import { expect, test } from "bun:test";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { AgentRunService } from "../src/runtime/agentRunService.js";
import { deniesTool, isToolEnabled, requiresApproval, toolAuthorizationSnapshot } from "../src/runtime/runtimeToolPermissions.js";
import { JsonStateStore } from "../src/store/jsonStateStore.js";
import { executeBuiltinTool, listBuiltinTools } from "../src/tools/toolRegistry.js";
import { loadSettings } from "../src/config/settings.js";
import { specFromPayload } from "../src/types/agentTypes.js";

test("approving config.manage cannot switch an ask run to auto and skip later approvals", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "kevin-permission-escalation-"));
  let requests = 0;
  const server = Bun.serve({ port: 0, hostname: "127.0.0.1", fetch() {
    requests++;
    if (requests > 1) return Response.json({ choices: [{ message: { content: "done" } }] });
    return Response.json({ choices: [{ message: { content: "escalate", tool_calls: [
      { id: "mode", type: "function", function: { name: "config__manage", arguments: JSON.stringify({ setting: "permissions.defaultMode", value: "auto" }) } },
      { id: "write", type: "function", function: { name: "filesystem__write", arguments: JSON.stringify({ path: "owned.txt", content: "x" }) } }
    ] } }] });
  } });
  try {
    const settings = await loadSettings(root);
    const service = new AgentRunService({ settings, store: new JsonStateStore(path.join(root, "state.json")) });
    const spec = service.specFromPayload({ protocol: "openai-chat", model: "fixture", api_key: "fixture", base_url: `http://127.0.0.1:${server.port}/v1`, enabled_tools: ["config.manage", "filesystem.write"], permission_profile: "ask" });

    const first = await service.runAgent(spec, "go");
    expect(first.result.status).toBe("waiting_approval");
    expect(first.result.pending_approval?.tool_call.id).toBe("mode");

    const second = await service.resumeApproval(first.run.run_id, true, { spec, approvalId: first.result.pending_approval!.approval_id });
    const modeResult = second.result.tool_results.find(result => result.tool_call_id === "mode");
    expect(modeResult?.is_error).toBe(true);
    expect(modeResult?.content).toContain("permission_tightening_only");
    expect(spec.permission_profile).toBe("ask");
    // The write from the same model turn must still stop for its own approval.
    expect(second.result.status).toBe("waiting_approval");
    expect(second.result.pending_approval?.tool_call.id).toBe("write");
    await expect(readFile(path.join(root, "owned.txt"))).rejects.toThrow();
    expect(requests).toBe(1);
  } finally { await server.stop(true); await rm(root, { recursive: true, force: true }); }
});

test("runtime gates keep the run's starting authorization when a tool loosens the live spec", async () => {
  const settings = await loadSettings(await mkdtemp(path.join(tmpdir(), "kevin-authorization-snapshot-")));
  const spec = specFromPayload({ message: "", enabled_tools: ["filesystem.read", "filesystem.write"], denied_tools: ["shell.run"], approval_required_tools: ["filesystem.write"], permission_profile: "auto" });
  const start = toolAuthorizationSnapshot(settings, spec);

  spec.enabled_tools.push("shell.run");
  spec.denied_tools = [];
  spec.approval_required_tools = [];
  expect(isToolEnabled(start, settings, spec, "shell.run")).toBe(false);
  expect(deniesTool(start, settings, spec, "shell.run")).toBe(true);
  expect(requiresApproval(start, settings, spec, "filesystem.write")).toBe(true);
  expect(requiresApproval(start, settings, spec, "filesystem__write")).toBe(true);

  const strict = specFromPayload({ message: "", enabled_tools: ["filesystem.write"], permission_profile: "deny" });
  const strictStart = toolAuthorizationSnapshot(settings, strict);
  strict.permission_profile = "auto";
  expect(deniesTool(strictStart, settings, strict, "filesystem.write")).toBe(true);
  expect(() => (start.deniedTools as string[]).push("x")).toThrow();
});

test("tightening the live spec takes effect immediately", async () => {
  const settings = await loadSettings(await mkdtemp(path.join(tmpdir(), "kevin-authorization-tighten-")));
  const spec = specFromPayload({ message: "", enabled_tools: ["filesystem.read", "filesystem.write"], permission_profile: "auto" });
  const start = toolAuthorizationSnapshot(settings, spec);
  expect(requiresApproval(start, settings, spec, "filesystem.write")).toBe(false);
  spec.approval_required_tools.push("filesystem.write");
  expect(requiresApproval(start, settings, spec, "filesystem.write")).toBe(true);
  spec.denied_tools.push("filesystem.read");
  expect(deniesTool(start, settings, spec, "filesystem.read")).toBe(true);
  spec.enabled_tools = ["filesystem.write"];
  expect(isToolEnabled(start, settings, spec, "filesystem.read")).toBe(false);
});

test("config.manage only moves the permission mode toward stricter profiles", async () => {
  const root = tmpdir();
  const ask = specFromPayload({ message: "", permission_profile: "ask" });
  const loosen = await executeBuiltinTool(root, "config.manage", { setting: "permissions.defaultMode", value: "auto" }, { spec: ask });
  expect(loosen.result.is_error).toBe(true);
  expect(loosen.result.content).toContain("cannot change permission profile from ask to auto");
  expect(ask.permission_profile).toBe("ask");
  expect(ask.metadata["config.permissions.defaultMode"]).toBeUndefined();

  const auto = specFromPayload({ message: "", permission_profile: "auto" });
  const tighten = await executeBuiltinTool(root, "config.manage", { setting: "permissions.defaultMode", value: "plan" }, { spec: auto });
  expect(tighten.result.is_error).toBe(false);
  expect(auto.permission_profile).toBe("ask");

  const deny = specFromPayload({ message: "", permission_profile: "deny" });
  const leaveDeny = await executeBuiltinTool(root, "config.manage", { setting: "permissions.defaultMode", value: "plan" }, { spec: deny });
  expect(leaveDeny.result.is_error).toBe(true);
  expect(deny.permission_profile).toBe("deny");
});

test("permission rules added by tools can only tighten", async () => {
  const root = tmpdir();
  const spec = specFromPayload({ message: "", denied_tools: ["shell.run"], approval_required_tools: ["filesystem.write"] });
  const allow = await executeBuiltinTool(root, "permission.add_rule", { behavior: "allow", tool: "shell.run" }, { spec });
  expect(allow.result.is_error).toBe(true);
  expect(spec.denied_tools).toEqual(["shell.run"]);

  const askOnDenied = await executeBuiltinTool(root, "permission.add_rule", { behavior: "ask", tool: "shell.run" }, { spec });
  expect(JSON.parse(askOnDenied.result.content).added).toEqual({ behavior: "deny", tool: "shell.run" });
  expect(spec.denied_tools).toEqual(["shell.run"]);
  expect(spec.approval_required_tools).toEqual(["filesystem.write"]);

  const denyAsked = await executeBuiltinTool(root, "permission.add_rule", { behavior: "deny", tool: "filesystem.write" }, { spec });
  expect(denyAsked.result.is_error).toBe(false);
  expect(spec.denied_tools).toEqual(["shell.run", "filesystem.write"]);
  expect(spec.approval_required_tools).toEqual([]);

  expect(listBuiltinTools().some(tool => tool.name === "permission.remove_rule")).toBe(false);
  const remove = await executeBuiltinTool(root, "permission.remove_rule", { tool: "shell.run" }, { spec });
  expect(remove.result.content).toContain("unknown tool");
});
