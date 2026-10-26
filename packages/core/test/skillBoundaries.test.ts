import { expect, test } from "bun:test";
import { mkdir, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { executeBuiltinTool, specFromPayload } from "../src/index.js";
import { discoverSkills, installSkill, loadSkill } from "../src/extensions/extensionManifests.js";
import { skillMetadataInstructions } from "../src/runtime/runtimeMessages.js";
import { parseSkillMarkdownManifest } from "../src/extensions/extensionSkillMarkdown.js";
import { executeRuntimeToolCall } from "../src/runtime/runtimeToolExecution.js";
import { toolAuthorizationSnapshot } from "../src/runtime/runtimeToolPermissions.js";
import { loadSettings } from "../src/config/settings.js";

const skill = (name: string, flags = "", body = "Use $ARGUMENTS literally.") => `---\nname: ${name}\ndescription: helper\n${flags}\n---\n${body}`;
async function workspace(run: (root: string, outside: string) => Promise<void>) {
  const root = await mkdtemp(path.join(tmpdir(), "kevin-skill-boundary-"));
  const outside = await mkdtemp(path.join(tmpdir(), "kevin-skill-outside-"));
  try { await run(root, outside); }
  finally { await rm(root, { recursive: true, force: true }); await rm(outside, { recursive: true, force: true }); }
}
async function put(root: string, name: string, content: string) {
  const folder = path.join(root, "skills", name);
  await mkdir(folder, { recursive: true });
  await writeFile(path.join(folder, "SKILL.md"), content);
  return folder;
}

test("model-only visibility differs from user slash visibility, and invocation prohibition is enforced", () => workspace(async root => {
  await put(root, "hidden", skill("hidden", "disable-model-invocation: true"));
  await put(root, "model", skill("model", "user-invocable: false"));
  const spec = specFromPayload({ message: "test" });
  const metadata = await skillMetadataInstructions(root, spec);
  expect(metadata).not.toContain("hidden:");
  expect(metadata).toContain("model:");
  for (const [tool, args] of [["skill.invoke", { skill: "hidden" }], ["skill.use", { name: "hidden" }]] as const) {
    const result = await executeBuiltinTool(root, tool, args, { spec });
    expect(result.result.is_error).toBe(true);
    expect(result.result.content).toContain("does not allow model invocation");
  }
}));

test("disabled skills stay disabled after serialization until explicitly re-enabled", () => workspace(async root => {
  const folder = await put(root, "helper", skill("helper"));
  let spec = specFromPayload({ message: "test" });
  await executeBuiltinTool(root, "skill.disable", { name: "helper" }, { spec });
  spec = structuredClone(spec);
  expect(await skillMetadataInstructions(root, spec)).not.toContain("helper:");
  expect((await executeBuiltinTool(root, "skill.invoke", { skill: "helper" }, { spec })).result.is_error).toBe(true);
  await executeBuiltinTool(root, "skill.use", { name: "helper" }, { spec });
  const invoked = await executeBuiltinTool(root, "skill.invoke", { skill: "helper", args: "$(touch must-not-exist)" }, { spec });
  expect(invoked.result.is_error).toBe(false);
  expect(JSON.parse(invoked.result.content).prompt).toContain("$(touch must-not-exist)");
  await expect(readFile(path.join(root, "must-not-exist"))).rejects.toThrow();
  await rm(folder, { recursive: true });
  expect((await executeBuiltinTool(root, "skill.disable", { name: "helper" }, { spec })).result.is_error).toBe(false);
}));

test("skill declarations cannot authorize a subsequent runtime file write", () => workspace(async root => {
  await put(root, "writer", skill("writer", "allowed-tools: [filesystem.write]"));
  const settings = await loadSettings(root);
  const spec = specFromPayload({ message: "test", enabled_tools: ["skill.use"], permission_profile: "auto" });
  await executeBuiltinTool(root, "skill.use", { name: "writer" }, { spec, settings });
  const execution = await executeRuntimeToolCall({ options: { settings }, spec, authorization: toolAuthorizationSnapshot(settings, spec), runId: "run", toolCall: { id: "write", name: "filesystem.write", arguments: { path: "blocked", content: "x" } }, messages: [], toolResults: [], runtimeEvents: [] });
  expect(execution.result.is_error).toBe(true);
  await expect(readFile(path.join(root, "blocked"))).rejects.toThrow();
}));

test("discovery does not follow roots or manifests outside the workspace/package", () => workspace(async (root, outside) => {
  await mkdir(path.join(outside, "hidden"));
  await writeFile(path.join(outside, "hidden", "SKILL.md"), skill("hidden", "", "secret outside instructions"));
  await symlink(outside, path.join(root, "skills"));
  expect(await discoverSkills({ repoRoot: root })).toEqual([]);
  await rm(path.join(root, "skills"));
  await mkdir(path.join(root, "skills", "escape"), { recursive: true });
  await symlink(path.join(outside, "hidden", "SKILL.md"), path.join(root, "skills", "escape", "SKILL.md"));
  const manifests = await discoverSkills({ repoRoot: root });
  expect(manifests[0].invalid).toBe(true);
  expect(JSON.stringify(manifests)).not.toContain("secret outside instructions");
  await expect(loadSkill({ repoRoot: root }, "escape")).rejects.toThrow();
}));

test("install rejects symlinked resources and symlinked destination roots", () => workspace(async (root, outside) => {
  const source = await put(root, "source", skill("source"));
  await writeFile(path.join(outside, "secret"), "secret");
  await symlink(path.join(outside, "secret"), path.join(source, "guide.md"));
  await expect(installSkill({ repoRoot: root }, source)).rejects.toThrow("links");
  await rm(path.join(source, "guide.md"));
  await symlink(outside, path.join(root, ".kevin"));
  await expect(installSkill({ repoRoot: root }, source)).rejects.toThrow("escapes");
  await expect(readFile(path.join(outside, "skills", "source", "SKILL.md"))).rejects.toThrow();
}));

test("concurrent installs reserve one destination and preserve its resources", () => workspace(async root => {
  const source = await put(root, "shared", skill("shared"));
  await mkdir(path.join(source, "references"));
  await writeFile(path.join(source, "references", "guide.md"), "reference content");
  const results = await Promise.allSettled([
    installSkill({ repoRoot: root }, source),
    installSkill({ repoRoot: root }, source)
  ]);
  expect(results.filter(result => result.status === "fulfilled")).toHaveLength(1);
  expect(results.filter(result => result.status === "rejected")).toHaveLength(1);
  const installed = path.join(root, ".kevin", "skills", "shared");
  expect(await readFile(path.join(installed, "references", "guide.md"), "utf8")).toBe("reference content");
  expect((await loadSkill({ repoRoot: root }, "shared")).rootPath).toBe(installed);
}));

test("oversized manifests, unsafe names and malformed invocation flags fail", () => workspace(async root => {
  await put(root, "large", skill("large", "", "x".repeat(256 * 1024)));
  expect((await discoverSkills({ repoRoot: root }))[0].invalid).toBe(true);
  await expect(loadSkill({ repoRoot: root }, "../large")).rejects.toThrow("invalid extension name");
  for (const flags of ["disable-model-invocation: maybe", "disable-model-invocation: true\ndisable-model-invocation: false", "__proto__: bad"]) {
    expect(() => parseSkillMarkdownManifest(skill("invalid", flags), "SKILL.md")).toThrow();
  }
}));

test("root precedence is deterministic and a malformed installed skill cannot fall back", () => workspace(async root => {
  await put(root, "same", skill("same", "", "repo version"));
  const installed = path.join(root, ".kevin", "skills", "same");
  await mkdir(installed, { recursive: true });
  await writeFile(path.join(installed, "SKILL.md"), skill("same", "", "installed version"));
  expect((await discoverSkills({ repoRoot: root })).filter(item => item.name === "same")).toHaveLength(1);
  expect((await loadSkill({ repoRoot: root }, "same")).instructions).toEqual(["installed version"]);
  await writeFile(path.join(installed, "SKILL.md"), "bad");
  await expect(loadSkill({ repoRoot: root }, "same")).rejects.toThrow();
}));
