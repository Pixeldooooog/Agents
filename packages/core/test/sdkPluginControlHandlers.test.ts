import { describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { AgentSdkClient, type SdkWireMessage } from "@agents/core/sdk";
import { JsonStateStore, loadSettings } from "../src/index.js";

describe("SDK plugin control handlers", () => {
  test("reloads plugin state from commands, extensions, and MCP records", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "agents-sdk-reload-plugins-"));
    try {
      await writeReloadPluginFixtures(root);
      const settings = await loadSettings(root);
      const store = new JsonStateStore(path.join(root, "state.json"));
      const scope = {
        tenantId: "tenant_1",
        userId: "user_1",
        agentId: "agent_1",
        workspaceId: "workspace_1"
      };
      await store.saveMcpServer({
        name: "docs-mcp",
        command: "bunx docs-mcp",
        transport: "stdio",
        url: "",
        headers: {},
        execution_mode: "trusted_control_plane",
        sandbox_profile: "",
        auth_required: false,
        auth_url: "",
        auth_status: "",
        auth_message: "",
        enabled: true,
        tenant_id: scope.tenantId,
        user_id: scope.userId,
        agent_id: scope.agentId,
        workspace_id: scope.workspaceId,
        created_at: 1,
        updated_at: 1
      });
      const client = new AgentSdkClient({ settings, store });

      const outputs = await collectWireMessages(client.runWireMessages([{
        type: "control_request",
        requestId: "reload_plugins_1",
        request: { subtype: "reload_plugins" }
      }], scope));
      const payload = controlPayload(outputs[0]);

      expect(payload.commands).toContainEqual(expect.objectContaining({
        name: "review",
        description: "Review code",
        aliases: ["inspect"]
      }));
      expect(payload.skills).toContainEqual(expect.objectContaining({
        name: "release-skill",
        version: "1.2.0",
        path: ".agents/skills/release",
        invalid: false
      }));
      expect(payload.plugins).toContainEqual(expect.objectContaining({
        name: "docs-plugin",
        version: "0.3.0",
        tools: ["mcp.resources"],
        path: ".agents/plugins/docs",
        invalid: false
      }));
      expect(payload.agents).toContainEqual(expect.objectContaining({
        name: "docs-agent",
        source: "plugin",
        extension: "docs-plugin",
        model: "docs-model"
      }));
      expect(payload.mcpServers).toContainEqual(expect.objectContaining({
        name: "docs-mcp",
        status: "connected"
      }));
      expect(payload.errorCount).toBe(1);
      expect(payload.error_count).toBe(1);
      expect(payload.errors).toContainEqual(expect.objectContaining({
        kind: "skill",
        name: "broken",
        manifestPath: ".agents/skills/broken/SKILL.md"
      }));
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });
});

async function writeReloadPluginFixtures(root: string): Promise<void> {
  await mkdir(path.join(root, ".agents/commands"), { recursive: true });
  await writeFile(path.join(root, ".agents/commands/review.md"), "---\ndescription: Review code\naliases: inspect\n---\nReview.");
  await mkdir(path.join(root, ".agents/skills/release"), { recursive: true });
  await writeFile(path.join(root, ".agents/skills/release/SKILL.md"), [
    "---",
    "name: release-skill",
    "version: 1.2.0",
    "description: Release workflow helper",
    "allowed-tools:",
    "  - filesystem.read",
    "---",
    "",
    "Use this skill for release workflow notes."
  ].join("\n"));
  await mkdir(path.join(root, ".agents/skills/broken"), { recursive: true });
  await writeFile(path.join(root, ".agents/skills/broken/SKILL.md"), "# Missing frontmatter\n");
  await mkdir(path.join(root, ".agents/plugins/docs/.codex-plugin"), { recursive: true });
  await writeFile(path.join(root, ".agents/plugins/docs/.codex-plugin/plugin.json"), JSON.stringify({
    name: "docs-plugin",
    version: "0.3.0",
    description: "Docs plugin",
    tools: ["mcp.resources"],
    prompt_fragments: ["prompt.md"],
    agent: "docs-agent",
    model: "docs-model"
  }));
}

async function collectWireMessages(messages: AsyncIterable<SdkWireMessage>): Promise<SdkWireMessage[]> {
  const collected: SdkWireMessage[] = [];
  for await (const message of messages) collected.push(message);
  return collected;
}

function controlPayload(message: SdkWireMessage): Record<string, any> {
  if (message.type !== "control_response" || message.response.subtype !== "success") {
    throw new Error("expected control success response");
  }
  return message.response.response as Record<string, any>;
}
