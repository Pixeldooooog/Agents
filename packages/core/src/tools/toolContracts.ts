import type { ToolPermissionDecision } from "../permissions/permissionDecisions.js";
import type { CommandExecutor, ExecutionPolicy } from "../ports/commandExecutor.js";
import type { AgentSpec } from "../types/agentTypes.js";
import type { JsonObject } from "../types/jsonTypes.js";
import type { Message, RuntimeEvent, ToolResult } from "../types/runtimeTypes.js";
import type { StateStore } from "../ports/stateStore.js";
import type { Settings } from "../config/settings.js";

/** Identity and limits every tool call receives; these are not services. */
export type ToolInvocation = {
  repoRoot: string;
  signal?: AbortSignal;
  spec?: AgentSpec;
  runId?: string;
  executionPolicy?: ExecutionPolicy;
};

export type TaskRunner = {
  run(taskId: string): Promise<unknown>;
  cancel(taskId: string): Promise<unknown>;
};

/** The live run history. Only context.compact and context.rewind modify `messages`; other tools read it. */
export type ToolConversationView = {
  messages: Message[];
  runtimeEvents: RuntimeEvent[];
};

/** Services a tool must declare before the registry passes them to its handler. */
export type ToolServices = {
  checkToolPermission: (name: string) => ToolPermissionDecision;
  settings: Settings;
  store: StateStore;
  commandExecutor: CommandExecutor;
  fileReadState: FileReadState;
  mcpProviders: McpProvider[];
  lspProvider: LspProvider;
  agentRunner: AgentRunner;
  taskRunner: TaskRunner;
  sleepWake: SleepWakeContext;
  conversation: ToolConversationView;
};

export type ToolCapability = keyof ToolServices;

/** What a handler sees: the invocation plus only the capabilities its definition declares. */
export type ToolContext<Required extends ToolCapability = never, Optional extends ToolCapability = never> =
  ToolInvocation & Pick<ToolServices, Required> & Partial<Pick<ToolServices, Optional>>;

/** Everything the runtime can offer a call; the registry narrows it per tool. */
export type ToolRuntimeContext = ToolInvocation & Partial<ToolServices> & {
  onToolStart?: (event: RuntimeEvent) => void | Promise<void>;
};

export type SleepWakeContext = {
  wait(milliseconds: number): Promise<boolean>;
  isWakeRequested(): boolean;
};

export type FileReadState = Record<string, FileReadStateRecord>;

export type FileReadStateRecord = {
  path: string;
  content: string;
  timestamp: number;
  encoding: string;
  fullRead: boolean;
  source: "read" | "write";
  offset: number;
  limit: number | null;
  isPartialView: boolean;
};

export type AgentRunner = {
  run(input: { spec: AgentSpec; prompt: string; runId: string; description: string }): Promise<{
    status: string;
    content: string;
    messages?: unknown[];
    tool_results?: unknown[];
  }>;
};

export type LspProvider = {
  query?: (request: Record<string, unknown>) => Promise<unknown> | unknown;
  clearDiagnostics?: (request: Record<string, unknown>) => Promise<unknown> | unknown;
  changeFile?: (request: Record<string, unknown>) => Promise<unknown> | unknown;
  saveFile?: (request: Record<string, unknown>) => Promise<unknown> | unknown;
} | ((request: Record<string, unknown>) => Promise<unknown> | unknown);

export type McpProvider = {
  server: {
    name: string;
    transport?: string;
    url?: string;
    command?: string;
    headers?: Record<string, string>;
    execution_mode?: string;
    auth_required?: boolean;
  };
  tools?: unknown[];
  callTool?: (name: string, args: Record<string, unknown>, signal?: AbortSignal) => Promise<unknown>;
  listResources?: (signal?: AbortSignal) => Promise<unknown[]>;
  list_resources?: (signal?: AbortSignal) => Promise<unknown[]>;
  readResource?: (uri: string, signal?: AbortSignal) => Promise<unknown>;
  read_resource?: (uri: string, signal?: AbortSignal) => Promise<unknown>;
  listPrompts?: (signal?: AbortSignal) => Promise<unknown[]>;
  list_prompts?: (signal?: AbortSignal) => Promise<unknown[]>;
  getPrompt?: (name: string, args: Record<string, unknown>, signal?: AbortSignal) => Promise<unknown>;
  get_prompt?: (name: string, args: Record<string, unknown>, signal?: AbortSignal) => Promise<unknown>;
  close?: () => Promise<void>;
};

export type ToolExecution = {
  events: RuntimeEvent[];
  result: ToolResult;
};

export type ToolDefinition<Required extends ToolCapability = never, Optional extends ToolCapability = never> = {
  name: string;
  description: string;
  risk: "low" | "medium" | "high";
  parameters: Record<string, unknown>;
  /** Capabilities the call fails without. */
  requires: readonly Required[];
  /** Capabilities the handler uses when present. */
  uses?: readonly Optional[];
  handler: (context: ToolContext<Required, Optional>, args: JsonObject) => Promise<unknown>;
};

/** Registry element type; each definition keeps its own narrowed handler context. */
export type RegisteredTool = ToolDefinition<ToolCapability, ToolCapability>;

/** Infers the declared capabilities so the handler is checked against exactly those. */
export function defineTool<const Required extends ToolCapability = never, const Optional extends ToolCapability = never>(
  definition: ToolDefinition<Required, Optional>
): RegisteredTool {
  return definition as unknown as RegisteredTool;
}

export type ToolFailure = {
  message: string;
};
