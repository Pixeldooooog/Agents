import { describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { executeBuiltinTool, loadSettings, specFromPayload } from "../src/index.js";

describe("instruction-only skill enablement", () => {
  for (const initialTools of [["shell.run"], []]) {
    test(`does not change explicit or default tool authority (${initialTools.length})`, async () => {
      const root = await mkdtemp(path.join(tmpdir(), "kevin-skill-authority-"));
      try {
        await writeSkill(root, "reader", { name: "reader", description: "read", allowedTools: ["filesystem.write"], disallowedTools: ["shell.run"] });
        const settings = await loadSettings(root);
        const spec = specFromPayload({ message: "test", enabled_tools: initialTools, denied_tools: ["filesystem.write"], approval_required_tools: ["shell.run"], permission_profile: "ask" });
        const authority = structuredClone({ enabled: spec.enabled_tools, denied: spec.denied_tools, approval: spec.approval_required_tools, profile: spec.permission_profile });
        const context = { spec, settings };
        await executeBuiltinTool(root, "skill.install", { source: "reader" }, context);
        for (const tool of ["skill.use", "skill.use", "skill.disable", "skill.use"]) {
          const result = await executeBuiltinTool(root, tool, { name: "reader" }, context);
          expect(result.result.is_error).toBe(false);
          expect(JSON.parse(result.result.content)).toMatchObject({ added_tools: [], removed_tools: [], restored_tools: [] });
          expect({ enabled: spec.enabled_tools, denied: spec.denied_tools, approval: spec.approval_required_tools, profile: spec.permission_profile }).toEqual(authority);
        }
      } finally { await rm(root, { recursive: true, force: true }); }
    });
  }
  test("skill toggles do not interfere with plugin-owned tools", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-skill-plugin-"));
    try {
      await writeSkill(root, "reader", { name: "reader", description: "reader", disallowedTools: ["mcp.resources"] });
      await writePlugin(root, "docs-plugin", ["mcp.resources"]);
      const spec = specFromPayload({ message: "test", enabled_tools: ["shell.run"] });
      const context = { spec };
      await executeBuiltinTool(root, "skill.install", { source: "reader" }, context);
      await executeBuiltinTool(root, "plugin.install", { source: "docs-plugin" }, context);
      await executeBuiltinTool(root, "skill.use", { name: "reader" }, context);
      await executeBuiltinTool(root, "plugin.enable", { name: "docs-plugin" }, context);
      expect(spec.enabled_tools).toEqual(["shell.run", "mcp.resources"]);
      await executeBuiltinTool(root, "skill.disable", { name: "reader" }, context);
      expect(spec.enabled_tools).toEqual(["shell.run", "mcp.resources"]);
      await executeBuiltinTool(root, "plugin.disable", { name: "docs-plugin" }, context);
      expect(spec.enabled_tools).toEqual(["shell.run"]);
    } finally { await rm(root, { recursive: true, force: true }); }
  });
});

type TestSkillManifest = {
  name: string;
  description: string;
  allowedTools?: string[];
  disallowedTools?: string[];
};

async function writeSkill(root: string, folder: string, manifest: TestSkillManifest): Promise<void> {
  await mkdir(path.join(root, folder), { recursive: true });
  await writeFile(path.join(root, folder, "SKILL.md"), [
    "---",
    `name: ${manifest.name}`,
    `description: ${manifest.description}`,
    ...toolList("allowed-tools", manifest.allowedTools || []),
    ...toolList("disallowed-tools", manifest.disallowedTools || []),
    "---",
    "",
    `Use ${manifest.name}.`
  ].join("\n"));
}

async function writePlugin(root: string, folder: string, tools: string[]): Promise<void> {
  await mkdir(path.join(root, folder, ".codex-plugin"), { recursive: true });
  await writeFile(path.join(root, folder, ".codex-plugin", "plugin.json"), JSON.stringify({
    name: folder,
    description: `${folder} plugin`,
    tools
  }));
}

function toolList(key: string, tools: string[]): string[] {
  return tools.length ? [`${key}:`, ...tools.map((tool) => `  - ${tool}`)] : [];
}
