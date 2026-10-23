import { describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { loadSettings, runtimeStartMessages, specFromPayload } from "../src/index.js";

describe("runtime start messages", () => {
  test("loads skill metadata without leaking skill bodies into startup context", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "agents-skill-context-"));
    try {
      await mkdir(path.join(root, ".agents", "skills", "release-helper"), { recursive: true });
      await writeFile(path.join(root, ".agents", "skills", "release-helper", "SKILL.md"), [
        "---",
        "name: release-helper",
        "description: Helps prepare release notes from repository changes.",
        "---",
        "",
        "Secret release body should load only through Skill."
      ].join("\n"));
      const settings = await loadSettings(root);
      const spec = specFromPayload({ message: "hello" });
      const messages = await runtimeStartMessages(settings, undefined, spec, "hello");
      const system = String(messages[0]?.content || "");
      expect(system).toContain("Available skills");
      expect(system).toContain("release-helper: Helps prepare release notes");
      expect(system).toContain("call the Skill tool");
      expect(system).not.toContain("Secret release body");

      const restricted = await runtimeStartMessages(settings, undefined, specFromPayload({ message: "hello", enabled_tools: ["filesystem.read"] }), "hello");
      expect(String(restricted[0]?.content || "")).not.toContain("Available skills");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });
});
