import { describe, expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { executeBuiltinTool, JsonStateStore, loadSettings, specFromPayload } from "../src/index.js";
import type { McpProvider } from "../src/toolContracts.js";

describe("MCP and meta tools", () => {
  test("searches registered tools by keyword and select syntax", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "agents-meta-tools-"));
    try {
      const search = await executeBuiltinTool(root, "tool.search", { query: "mcp resource", include_all: true });
      const matches = JSON.parse(search.result.content).matches.map((match: { name: string }) => match.name);
      expect(matches).toContain("mcp.resources");

      const selected = await executeBuiltinTool(root, "tool.search", { query: "select:mcp.resources", include_all: true });
      expect(JSON.parse(selected.result.content).matches.map((match: { name: string }) => match.name)).toEqual(["mcp.resources"]);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("persists MCP server config and reads provider resources and prompts", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "agents-mcp-tools-"));
    try {
      const settings = await loadSettings(root);
      const store = new JsonStateStore(path.join(root, "state.json"));
      const spec = specFromPayload({ message: "mcp", tenant_id: "tenant", user_id: "user", agent_id: "agent", workspace_id: "workspace" });
      const provider: McpProvider = {
        server: { name: "docs", transport: "stdio", command: "docs-server" },
        listResources: async () => [{ uri: "docs://intro", name: "Intro", description: "Intro docs", mimeType: "text/markdown" }],
        readResource: async (uri) => `content:${uri}`,
        listPrompts: async () => [{ name: "release", description: "Release prompt", arguments: [{ name: "version", required: true }] }],
        getPrompt: async (name, args) => `${name}:${args.version}`
      };
      const context = { settings, store, spec, mcpProviders: [provider] };

      const configured = await executeBuiltinTool(root, "mcp.configure", { name: "docs", command: "docs-server", transport: "stdio" }, context);
      const configuredPayload = JSON.parse(configured.result.content);
      expect(configuredPayload.configured.name).toBe("docs");
      expect(configuredPayload.servers[0].enabled).toBe(true);

      const resources = await executeBuiltinTool(root, "mcp.resources", { server: "docs" }, context);
      expect(JSON.parse(resources.result.content).resources[0].uri).toBe("docs://intro");

      const resource = await executeBuiltinTool(root, "mcp.read_resource", { server: "docs", uri: "docs://intro" }, context);
      expect(JSON.parse(resource.result.content).content).toBe("content:docs://intro");

      const prompts = await executeBuiltinTool(root, "mcp.prompts", { query: "release" }, context);
      expect(JSON.parse(prompts.result.content).prompts[0].name).toBe("release");

      const prompt = await executeBuiltinTool(root, "mcp.get_prompt", { name: "release", server: "docs", arguments: { version: "v1" } }, context);
      expect(JSON.parse(prompt.result.content).content).toBe("release:v1");

      const disabled = await executeBuiltinTool(root, "mcp.disable", { name: "docs" }, context);
      expect(JSON.parse(disabled.result.content).disabled).toBe("docs");
      expect((await store.listMcpServers({ tenant_id: "tenant", user_id: "user", agent_id: "agent", workspace_id: "workspace" }))[0].enabled).toBe(false);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });
});
