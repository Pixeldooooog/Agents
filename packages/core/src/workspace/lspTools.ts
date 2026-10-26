import { stat } from "node:fs/promises";
import path from "node:path";
import type { JsonObject } from "../types/jsonTypes.js";
import { defineTool, type LspProvider, type RegisteredTool, type ToolContext } from "../tools/toolContracts.js";
import { numberArg, resolveWorkspacePath, stringArg } from "../tools/toolInputs.js";

const lspOperations = [
  "goToDefinition",
  "findReferences",
  "hover",
  "documentSymbol",
  "workspaceSymbol",
  "goToImplementation",
  "prepareCallHierarchy",
  "incomingCalls",
  "outgoingCalls"
];

const maxLspFileSizeBytes = 10 * 1024 * 1024;

const lspQuerySchema = {
  type: "object",
  properties: {
    operation: { type: "string", enum: lspOperations },
    filePath: { type: "string" },
    line: { type: "integer", minimum: 1 },
    character: { type: "integer", minimum: 1 }
  },
  required: ["operation", "filePath", "line", "character"],
  additionalProperties: false
};

export const lspToolDefinitions: RegisteredTool[] = [
  defineTool({
    name: "lsp.query",
    description: "Run a read-only language-server query for a source file.",
    risk: "low",
    parameters: lspQuerySchema,
    requires: [],
    uses: ["lspProvider"],
    handler: lspQuery
  })
];

async function lspQuery(context: ToolContext<never, "lspProvider">, args: JsonObject) {
  const operation = stringArg(args.operation);
  if (!lspOperations.includes(operation)) throw new Error(`Unsupported LSP operation: ${operation}`);
  const line = numberArg(args.line, 0);
  const character = numberArg(args.character, 0);
  if (line < 1) throw new Error("line must be a positive integer");
  if (character < 1) throw new Error("character must be a positive integer");
  const filePath = stringArg(args.filePath);
  const absolutePath = resolveWorkspacePath(context.repoRoot, filePath);
  const info = await stat(absolutePath);
  if (!info.isFile()) throw new Error(`Path is not a file: ${filePath}`);
  if (info.size > maxLspFileSizeBytes) {
    return lspPayload(operation, filePath, `File too large for LSP analysis (${Math.ceil(info.size / (1024 * 1024))}MB exceeds 10MB limit)`);
  }
  const provider = context.lspProvider;
  if (!provider) return noLspServerPayload(operation, filePath);
  const result = await queryProvider(provider, { operation, filePath, absolutePath, line, character });
  if (result === undefined || result === null) return noLspServerPayload(operation, filePath);
  return coerceLspResponse(result, operation, filePath);
}

async function queryProvider(provider: LspProvider, request: Record<string, unknown>): Promise<unknown> {
  if (typeof provider === "function") return provider(request);
  if (provider.query) return provider.query(request);
  throw new Error("LSP provider must expose query(...) or be callable");
}

function coerceLspResponse(response: unknown, operation: string, filePath: string) {
  if (response && typeof response === "object" && !Array.isArray(response)) {
    const payload = response as Record<string, unknown>;
    return {
      operation: String(payload.operation || operation),
      filePath: String(payload.filePath || filePath),
      result: String(payload.result || ""),
      ...(payload.resultCount !== undefined ? { resultCount: Number(payload.resultCount) } : {}),
      ...(payload.fileCount !== undefined ? { fileCount: Number(payload.fileCount) } : {})
    };
  }
  return lspPayload(operation, filePath, typeof response === "string" ? response : JSON.stringify(response));
}

function noLspServerPayload(operation: string, filePath: string) {
  return lspPayload(operation, filePath, `No LSP server available for file type: ${path.extname(filePath)}`);
}

function lspPayload(operation: string, filePath: string, result: string) {
  return { operation, result, filePath };
}
