import { createHash } from "node:crypto";
import { defineTool, type McpProvider, type RegisteredTool } from "../tools/toolContracts.js";
import { prepareToolValidator } from "../tools/toolValidation.js";
import { boundedToolContent } from "../tools/toolOutput.js";
import { callMcpProvider, isMcpProviderActive } from "./mcpProviderLifecycle.js";

const catalog = new WeakMap<McpProvider, RegisteredTool[]>();

export function mcpExternalTools(providers: McpProvider[] = []): RegisteredTool[] {
  const names = new Set<string>();
  return providers.filter(isMcpProviderActive).flatMap(provider => {
    if (names.has(provider.server.name)) throw new Error(`duplicate MCP server name: ${provider.server.name}`);
    names.add(provider.server.name);
    let definitions = catalog.get(provider);
    if (!definitions) {
      const seen = new Set<string>();
      definitions = (provider.tools || []).map(raw => {
        if (!raw || typeof raw !== "object" || !("name" in raw) || typeof raw.name !== "string" || !raw.name.trim() || seen.has(raw.name)) throw new Error("invalid or duplicate MCP tool name");
        seen.add(raw.name);
        if (!("inputSchema" in raw) || !raw.inputSchema || typeof raw.inputSchema !== "object" || Array.isArray(raw.inputSchema) || !("type" in raw.inputSchema) || raw.inputSchema.type !== "object") throw new Error("MCP tool inputSchema must be an object schema");
        const remoteName = raw.name;
        const parameters = structuredClone(raw.inputSchema) as Record<string, unknown>;
        const description = "description" in raw && typeof raw.description === "string" ? raw.description : "";
        // Identity includes the approved schema/description; reconnect cannot silently change a pending action.
        const identity = JSON.stringify([provider.server.name, remoteName, parameters, description]);
        if (Buffer.byteLength(identity) > 256 * 1024) throw new Error("MCP tool definition exceeds 256 KiB");
        const definition = defineTool({
          name: `mcp_${createHash("sha256").update(identity).digest("hex").slice(0, 56)}`,
          description: `[MCP ${provider.server.name}/${remoteName}] ${description}`,
          risk: "high", parameters,
          requires: [],
          uses: ["settings"],
          handler: async (context, args) => {
            if (!provider.callTool) throw new Error("MCP provider does not support tool calls");
            const { tool_call_id: _correlation, ...input } = args;
            const result = await callMcpProvider(context, provider, signal => provider.callTool!(remoteName, input, signal));
            if (!result || typeof result !== "object" || !("content" in result) || !Array.isArray(result.content)) throw new Error("invalid MCP tool result");
            if ("isError" in result && result.isError === true) throw new Error(boundedToolContent(result));
            return result;
          }
        });
        prepareToolValidator(definition);
        return definition;
      });
      catalog.set(provider, definitions);
    }
    return definitions;
  });
}
