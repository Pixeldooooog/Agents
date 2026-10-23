import { describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { executeBuiltinTool, loadSettings, specFromPayload } from "../src/index.js";

describe("extension tool enablement", () => {
  test("keeps overlapping skill tool permissions stable", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "agents-skill-overlap-tools-"));
    try {
      for (const name of ["shared-a", "shared-b"]) {
        await writeSkill(root, name, {
          name,
          description: `${name} skill`,
          allowedTools: ["filesystem.read"],
          disallowedTools: ["shell.run"]
        });
      }
      const spec = specFromPayload({ message: "overlap skills", enabled_tools: ["shell.run"] });
      const context = { spec };
      await executeBuiltinTool(root, "skill.install", { source: "shared-a" }, context);
      await executeBuiltinTool(root, "skill.install", { source: "shared-b" }, context);

      const usedA = await executeBuiltinTool(root, "skill.use", { name: "shared-a" }, context);
      expect(JSON.parse(usedA.result.content).added_tools).toEqual(["filesystem.read"]);
      expect(JSON.parse(usedA.result.content).removed_tools).toEqual(["shell.run"]);
      expect(spec.enabled_tools).toEqual(["filesystem.read"]);

      const usedAAgain = await executeBuiltinTool(root, "skill.use", { name: "shared-a" }, context);
      expect(JSON.parse(usedAAgain.result.content).added_tools).toEqual([]);
      expect(JSON.parse(usedAAgain.result.content).removed_tools).toEqual([]);
      expect(spec.enabled_tools).toEqual(["filesystem.read"]);

      const usedB = await executeBuiltinTool(root, "skill.use", { name: "shared-b" }, context);
      expect(JSON.parse(usedB.result.content).added_tools).toEqual([]);
      expect(JSON.parse(usedB.result.content).removed_tools).toEqual([]);
      expect(spec.enabled_tools).toEqual(["filesystem.read"]);

      const disabledA = await executeBuiltinTool(root, "skill.disable", { name: "shared-a" }, context);
      expect(JSON.parse(disabledA.result.content).removed_tools).toEqual([]);
      expect(JSON.parse(disabledA.result.content).restored_tools).toEqual([]);
      expect(spec.enabled_tools).toEqual(["filesystem.read"]);

      const disabledB = await executeBuiltinTool(root, "skill.disable", { name: "shared-b" }, context);
      expect(JSON.parse(disabledB.result.content).removed_tools).toEqual(["filesystem.read"]);
      expect(JSON.parse(disabledB.result.content).restored_tools).toEqual(["shell.run"]);
      expect(spec.enabled_tools).toEqual(["shell.run"]);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("keeps skill and plugin tool ownership stable when enablement is interleaved", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "agents-skill-plugin-interleave-"));
    try {
      await writeSkill(root, "reader", {
        name: "reader",
        description: "Reader skill",
        allowedTools: ["filesystem.read"]
      });
      await writePlugin(root, "docs-plugin", ["mcp.resources"]);
      const spec = specFromPayload({ message: "interleave", enabled_tools: [] });
      const context = { spec };
      await executeBuiltinTool(root, "skill.install", { source: "reader" }, context);
      await executeBuiltinTool(root, "plugin.install", { source: "docs-plugin" }, context);

      const used = await executeBuiltinTool(root, "skill.use", { name: "reader" }, context);
      expect(JSON.parse(used.result.content).added_tools).toEqual(["filesystem.read"]);
      expect(spec.enabled_tools).toEqual(["filesystem.read"]);

      const pluginEnabled = await executeBuiltinTool(root, "plugin.enable", { name: "docs-plugin" }, context);
      expect(JSON.parse(pluginEnabled.result.content).added_tools).toEqual(["mcp.resources"]);
      expect(spec.enabled_tools).toEqual(["mcp.resources", "filesystem.read"]);

      const skillDisabled = await executeBuiltinTool(root, "skill.disable", { name: "reader" }, context);
      expect(JSON.parse(skillDisabled.result.content).removed_tools).toEqual(["filesystem.read"]);
      expect(spec.enabled_tools).toEqual(["mcp.resources"]);

      const pluginDisabled = await executeBuiltinTool(root, "plugin.disable", { name: "docs-plugin" }, context);
      expect(JSON.parse(pluginDisabled.result.content).removed_tools).toEqual(["mcp.resources"]);
      expect(spec.enabled_tools).toEqual([]);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("tracks plugin-owned tools even when an active skill suppresses them", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "agents-skill-plugin-suppressed-"));
    try {
      await writeBlockingSkill(root);
      await writePlugin(root, "docs-plugin", ["mcp.resources"]);
      const spec = specFromPayload({ message: "suppressed", enabled_tools: ["shell.run"] });
      const context = { spec };
      await executeBuiltinTool(root, "skill.install", { source: "blocker" }, context);
      await executeBuiltinTool(root, "plugin.install", { source: "docs-plugin" }, context);

      await executeBuiltinTool(root, "skill.use", { name: "blocker" }, context);
      expect(spec.enabled_tools).toEqual(["shell.run", "filesystem.read"]);

      const pluginEnabled = await executeBuiltinTool(root, "plugin.enable", { name: "docs-plugin" }, context);
      expect(JSON.parse(pluginEnabled.result.content).added_tools).toEqual([]);
      expect(spec.enabled_tools).toEqual(["shell.run", "filesystem.read"]);

      const skillDisabled = await executeBuiltinTool(root, "skill.disable", { name: "blocker" }, context);
      const skillDisabledPayload = JSON.parse(skillDisabled.result.content);
      expect(skillDisabledPayload.removed_tools).toEqual(["filesystem.read"]);
      expect(skillDisabledPayload.restored_tools).toEqual(["mcp.resources"]);
      expect(spec.enabled_tools).toEqual(["shell.run", "mcp.resources"]);

      const pluginDisabled = await executeBuiltinTool(root, "plugin.disable", { name: "docs-plugin" }, context);
      expect(JSON.parse(pluginDisabled.result.content).removed_tools).toEqual(["mcp.resources"]);
      expect(spec.enabled_tools).toEqual(["shell.run"]);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("does not treat pre-enabled plugin tools as the skill baseline", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "agents-plugin-before-skill-"));
    try {
      await writeBlockingSkill(root);
      await writePlugin(root, "docs-plugin", ["mcp.resources"]);
      const spec = specFromPayload({ message: "plugin before skill", enabled_tools: ["shell.run"] });
      const context = { spec };
      await executeBuiltinTool(root, "plugin.install", { source: "docs-plugin" }, context);
      await executeBuiltinTool(root, "skill.install", { source: "blocker" }, context);

      await executeBuiltinTool(root, "plugin.enable", { name: "docs-plugin" }, context);
      expect(spec.enabled_tools).toEqual(["shell.run", "mcp.resources"]);

      const skillEnabled = await executeBuiltinTool(root, "skill.use", { name: "blocker" }, context);
      const skillEnabledPayload = JSON.parse(skillEnabled.result.content);
      expect(skillEnabledPayload.added_tools).toEqual(["filesystem.read"]);
      expect(skillEnabledPayload.removed_tools).toEqual(["mcp.resources"]);
      expect(spec.enabled_tools).toEqual(["shell.run", "filesystem.read"]);

      const pluginDisabled = await executeBuiltinTool(root, "plugin.disable", { name: "docs-plugin" }, context);
      expect(JSON.parse(pluginDisabled.result.content).removed_tools).toEqual([]);
      expect(spec.enabled_tools).toEqual(["shell.run", "filesystem.read"]);

      const skillDisabled = await executeBuiltinTool(root, "skill.disable", { name: "blocker" }, context);
      const skillDisabledPayload = JSON.parse(skillDisabled.result.content);
      expect(skillDisabledPayload.removed_tools).toEqual(["filesystem.read"]);
      expect(skillDisabledPayload.restored_tools).toEqual([]);
      expect(spec.enabled_tools).toEqual(["shell.run"]);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("uses configured default tools as the skill baseline when spec tools are empty", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "agents-skill-default-tools-"));
    try {
      await mkdir(path.join(root, "config"), { recursive: true });
      await writeFile(path.join(root, "config", "defaults.toml"), [
        "[agent]",
        "builtin_tools = \"shell.run,filesystem.read\""
      ].join("\n"));
      await writeSkill(root, "writer", {
        name: "writer",
        description: "Writer skill",
        allowedTools: ["filesystem.write"],
        disallowedTools: ["shell.run"]
      });
      const settings = await loadSettings(root);
      const spec = specFromPayload({ message: "defaults", enabled_tools: [] });
      const context = { spec, settings };
      await executeBuiltinTool(root, "skill.install", { source: "writer" }, context);

      const used = await executeBuiltinTool(root, "skill.use", { name: "writer" }, context);
      const usedPayload = JSON.parse(used.result.content);
      expect(usedPayload.added_tools).toEqual(["filesystem.write"]);
      expect(usedPayload.removed_tools).toEqual(["shell.run"]);
      expect(spec.enabled_tools).toEqual(["filesystem.read", "filesystem.write"]);

      const disabled = await executeBuiltinTool(root, "skill.disable", { name: "writer" }, context);
      const disabledPayload = JSON.parse(disabled.result.content);
      expect(disabledPayload.removed_tools).toEqual(["filesystem.write"]);
      expect(disabledPayload.restored_tools).toEqual(["shell.run"]);
      expect(spec.enabled_tools).toEqual(["shell.run", "filesystem.read"]);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });
});

type TestSkillManifest = {
  name: string;
  description: string;
  allowedTools?: string[];
  disallowedTools?: string[];
};

async function writeBlockingSkill(root: string): Promise<void> {
  await writeSkill(root, "blocker", {
    name: "blocker",
    description: "Blocks MCP resources while active",
    allowedTools: ["filesystem.read"],
    disallowedTools: ["mcp.resources"]
  });
}

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
