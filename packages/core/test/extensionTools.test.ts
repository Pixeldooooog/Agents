import { describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { executeBuiltinTool, specFromPayload } from "../src/index.js";

describe("skill and plugin extension tools", () => {
  test("installs, discovers, invokes, enables, disables, and uninstalls a standard SKILL.md skill", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-standard-skill-tools-"));
    try {
      await mkdir(path.join(root, "source-standard-skill"), { recursive: true });
      await mkdir(path.join(root, "source-standard-skill", "references"), { recursive: true });
      await writeFile(path.join(root, "source-standard-skill", "SKILL.md"), [
        "---",
        "name: release-standard",
        "version: 2.0.0",
        "description: |",
        "  Standard release helper.",
        "  Keeps release notes consistent.",
        "when-to-use: Use when preparing release notes from repository changes.",
        "allowed-tools:",
        "  - filesystem.read",
        "  - shell.run",
        "disallowed-tools:",
        "  - filesystem.write",
        "paths:",
        "  - src/**/*.ts",
        "context: fork",
        "model: gpt-test",
        "disable-model-invocation: true",
        "---",
        "",
        "# Release Standard",
        "",
        "See references/guide.md.",
        "",
        "Prepare release notes for $ARGUMENTS."
      ].join("\n"));
      await writeFile(path.join(root, "source-standard-skill", "references", "guide.md"), "Release guide.");
      const spec = specFromPayload({ message: "standard skill", enabled_tools: ["shell.run", "filesystem.write"] });
      const context = { spec };

      const installed = await executeBuiltinTool(root, "skill.install", { source: "source-standard-skill" }, context);
      const installedSkill = JSON.parse(installed.result.content).skill;
      expect(installedSkill.name).toBe("release-standard");
      expect(installedSkill.format).toBe("skill-md");
      expect(installedSkill.description).toContain("Standard release helper");
      expect(installedSkill.prompt_fragments).toEqual(["SKILL.md"]);
      expect(installedSkill.allowed_tools).toEqual(["filesystem.read", "shell.run"]);

      const discovered = await executeBuiltinTool(root, "skill.discover", { query: "repository changes", include_prompt: true }, context);
      const discoveredPayload = JSON.parse(discovered.result.content);
      const discoveredSkill = discoveredPayload.skills[0];
      expect(discoveredSkill.name).toBe("release-standard");
      expect(discoveredSkill.when_to_use).toContain("release notes");
      expect(discoveredSkill.paths).toEqual(["src/**/*.ts"]);
      expect(discoveredSkill.prompts).toEqual(["SKILL.md"]);
      expect(discovered.result.content).not.toContain("Prepare release notes for");

      const invoked = await executeBuiltinTool(root, "skill.invoke", { skill: "release-standard", args: "v2" }, context);
      const invokedSkill = JSON.parse(invoked.result.content);
      expect(invokedSkill.prompt).toContain("v2");
      expect(invokedSkill.prompt).toContain("references/guide.md");
      expect(invokedSkill.skill.path).toBe(".kevin/skills/release-standard");
      expect(invokedSkill.path).toBe(".kevin/skills/release-standard");
      expect(invokedSkill.manifestPath).toBe(".kevin/skills/release-standard/SKILL.md");
      expect(invokedSkill.allowedTools).toEqual(["filesystem.read", "shell.run"]);
      expect(invokedSkill.disallowedTools).toEqual(["filesystem.write"]);
      expect(invokedSkill.model).toBe("gpt-test");
      expect(invokedSkill.status).toBe("fork_unavailable");
      expect(invokedSkill.disableModelInvocation).toBe(true);

      const used = await executeBuiltinTool(root, "skill.use", { name: "release-standard" }, context);
      const usedPayload = JSON.parse(used.result.content);
      expect(usedPayload.enabled).toBe(true);
      expect(usedPayload.added_tools).toEqual(["filesystem.read"]);
      expect(usedPayload.removed_tools).toEqual(["filesystem.write"]);
      expect(spec.enabled_tools).toEqual(["shell.run", "filesystem.read"]);

      const disabled = await executeBuiltinTool(root, "skill.disable", { name: "release-standard" }, context);
      const disabledPayload = JSON.parse(disabled.result.content);
      expect(disabledPayload.enabled).toBe(false);
      expect(disabledPayload.removed_tools).toEqual(["filesystem.read"]);
      expect(disabledPayload.restored_tools).toEqual(["filesystem.write"]);
      expect(spec.enabled_tools).toEqual(["shell.run", "filesystem.write"]);

      const uninstalled = await executeBuiltinTool(root, "skill.uninstall", { name: "release-standard" }, context);
      expect(JSON.parse(uninstalled.result.content).uninstalled).toBe(true);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("rejects legacy skill.json skill packages", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-legacy-skill-tools-"));
    try {
      await mkdir(path.join(root, "legacy-skill"), { recursive: true });
      await writeFile(path.join(root, "legacy-skill", "skill.json"), JSON.stringify({
        name: "legacy-helper",
        description: "Legacy helper",
        prompt_fragments: ["legacy"]
      }));
      const spec = specFromPayload({ message: "legacy skill", enabled_tools: [] });

      const installed = await executeBuiltinTool(root, "skill.install", { source: "legacy-skill" }, { spec });
      expect(installed.result.is_error).toBe(true);
      expect(installed.result.content).toContain("skill manifest not found");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("rejects non-standard SKILL.md files", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-invalid-skill-tools-"));
    try {
      await mkdir(path.join(root, "missing-frontmatter"), { recursive: true });
      await writeFile(path.join(root, "missing-frontmatter", "SKILL.md"), "# Missing frontmatter\n");
      await mkdir(path.join(root, "missing-description"), { recursive: true });
      await writeFile(path.join(root, "missing-description", "SKILL.md"), [
        "---",
        "name: missing-description",
        "---",
        "",
        "Use this skill."
      ].join("\n"));
      await mkdir(path.join(root, "invalid-name"), { recursive: true });
      await writeFile(path.join(root, "invalid-name", "SKILL.md"), [
        "---",
        "name: invalid name",
        "description: Invalid name",
        "---",
        "",
        "Use this skill."
      ].join("\n"));
      await mkdir(path.join(root, "empty-body"), { recursive: true });
      await writeFile(path.join(root, "empty-body", "SKILL.md"), [
        "---",
        "name: empty-body",
        "description: Empty body",
        "---",
        ""
      ].join("\n"));

      const spec = specFromPayload({ message: "invalid skill", enabled_tools: [] });
      const missingFrontmatter = await executeBuiltinTool(root, "skill.install", { source: "missing-frontmatter" }, { spec });
      expect(missingFrontmatter.result.is_error).toBe(true);
      expect(missingFrontmatter.result.content).toContain("requires YAML frontmatter");

      const missingDescription = await executeBuiltinTool(root, "skill.install", { source: "missing-description" }, { spec });
      expect(missingDescription.result.is_error).toBe(true);
      expect(missingDescription.result.content).toContain("requires description");

      const invalidName = await executeBuiltinTool(root, "skill.install", { source: "invalid-name" }, { spec });
      expect(invalidName.result.is_error).toBe(true);
      expect(invalidName.result.content).toContain("skill name must contain only");

      const emptyBody = await executeBuiltinTool(root, "skill.install", { source: "empty-body" }, { spec });
      expect(emptyBody.result.is_error).toBe(true);
      expect(emptyBody.result.content).toContain("skill body is required");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("supports single-file SKILL.md installs and lowercase skill.md packages", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-skill-file-tools-"));
    try {
      await mkdir(path.join(root, "single-source"), { recursive: true });
      await writeFile(path.join(root, "single-source", "SKILL.md"), [
        "---",
        "name: single-file",
        "description: Single file skill",
        "---",
        "",
        "Use single file skill for $ARGUMENTS."
      ].join("\n"));
      await mkdir(path.join(root, "lower-source"), { recursive: true });
      await writeFile(path.join(root, "lower-source", "skill.md"), [
        "---",
        "name: lower-skill",
        "description: >-",
        "  Lower skill summary",
        "  continues here.",
        "---",
        "",
        "Use lowercase skill."
      ].join("\n"));
      const spec = specFromPayload({ message: "file skills", enabled_tools: [] });
      const context = { spec };

      const singleInstalled = await executeBuiltinTool(root, "skill.install", { source: "single-source/SKILL.md" }, context);
      const singleSkill = JSON.parse(singleInstalled.result.content).skill;
      expect(singleSkill.name).toBe("single-file");
      expect(singleSkill.path).toBe(".kevin/skills/single-file");
      expect(singleSkill.manifest_path).toBe(".kevin/skills/single-file/SKILL.md");

      const lowerInstalled = await executeBuiltinTool(root, "skill.install", { source: "lower-source" }, context);
      const lowerSkill = JSON.parse(lowerInstalled.result.content).skill;
      expect(lowerSkill.name).toBe("lower-skill");
      expect(lowerSkill.description).toBe("Lower skill summary continues here.");
      expect(lowerSkill.prompt_fragments).toEqual(["skill.md"]);

      const singleInvoked = await executeBuiltinTool(root, "skill.invoke", { skill: "single-file", args: "docs" }, context);
      expect(JSON.parse(singleInvoked.result.content).prompt).toContain("docs");

      const lowerInvoked = await executeBuiltinTool(root, "skill.invoke", { skill: "lower-skill" }, context);
      expect(JSON.parse(lowerInvoked.result.content).prompt).toContain("lowercase skill");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("installs, discovers, enables, disables, and uninstalls a plugin", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-plugin-tools-"));
    try {
      await mkdir(path.join(root, "source-plugin", ".codex-plugin"), { recursive: true });
      await writeFile(path.join(root, "source-plugin", ".codex-plugin", "plugin.json"), JSON.stringify({
        name: "docs-plugin",
        version: "0.2.0",
        description: "Docs plugin",
        tools: ["mcp.resources"],
        prompt_fragments: ["prompt.md"]
      }));
      await writeFile(path.join(root, "source-plugin", "prompt.md"), "Use docs plugin.");
      const spec = specFromPayload({ message: "plugins", enabled_tools: [] });
      const context = { spec };

      const installed = await executeBuiltinTool(root, "plugin.install", { source: "source-plugin" }, context);
      expect(JSON.parse(installed.result.content).plugin.name).toBe("docs-plugin");

      const discovered = await executeBuiltinTool(root, "plugin.discover", { query: "docs", include_prompt: true }, context);
      expect(JSON.parse(discovered.result.content).plugins[0].prompt_fragments[0]).toBe("prompt.md");

      const enabled = await executeBuiltinTool(root, "plugin.enable", { name: "docs-plugin" }, context);
      expect(JSON.parse(enabled.result.content).enabled).toBe(true);
      expect(spec.enabled_tools).toContain("mcp.resources");

      const disabled = await executeBuiltinTool(root, "plugin.disable", { name: "docs-plugin" }, context);
      expect(JSON.parse(disabled.result.content).enabled).toBe(false);

      const uninstalled = await executeBuiltinTool(root, "plugin.uninstall", { name: "docs-plugin" }, context);
      expect(JSON.parse(uninstalled.result.content).uninstalled).toBe(true);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });
});
