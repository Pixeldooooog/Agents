import { expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import path from "node:path";
import { tmpdir } from "node:os";
import { loadSettings } from "../src/config/settings.js";
import { specFromPayload } from "../src/types/agentTypes.js";
import { toolAuthorizationSnapshot, runtimePermissionDecision, requiresApproval, deniesTool } from "../src/runtime/runtimeToolPermissions.js";
import { executeBuiltinTool } from "../src/tools/toolRegistry.js";

test("explanation and execution share disabled, alias, MCP and hook decisions with immutable authority", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "kevin-permission-decision-"));
  try {
    const settings = await loadSettings(root);
    const external = `mcp_${"a".repeat(56)}`;
    const spec = specFromPayload({ message: "", permission_profile: "auto", enabled_tools: ["permission.explain", "hook.add", "filesystem.write", external], approval_required_tools: ["filesystem.write"] });
    const start = toolAuthorizationSnapshot(settings, spec);
    spec.approval_required_tools = [];
    for (const name of ["hook__add", "filesystem__write", external, "shell.run"]) {
      const decision = runtimePermissionDecision(start, settings, spec, name);
      const explained = await executeBuiltinTool(root, "permission.explain", { tool: name }, { spec, checkToolPermission: tool => runtimePermissionDecision(start, settings, spec, tool) });
      expect(JSON.parse(explained.result.content).decision).toEqual(decision);
      expect(requiresApproval(start, settings, spec, name)).toBe(decision.behavior === "ask");
      expect(deniesTool(start, settings, spec, name)).toBe(decision.behavior === "deny");
    }
    spec.denied_tools.push("hook.add");
    expect(runtimePermissionDecision(start, settings, spec, "hook__add").behavior).toBe("deny");
  } finally { await rm(root, { recursive: true, force: true }); }
});
