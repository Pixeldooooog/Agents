import type { CommandExecutor, ExecutionPolicy } from "../ports/commandExecutor.js";
import type { AgentSpec } from "../types/agentTypes.js";
import type { JsonObject } from "../types/jsonTypes.js";
import type { Message, RuntimeEvent, ToolResult } from "../types/runtimeTypes.js";
import type { StateStore } from "../ports/stateStore.js";
import type { Settings } from "../config/settings.js";

export type ToolExecutionContext = {
  repoRoot: string;
  signal?: AbortSignal;
  commandExecutor?: CommandExecutor;
  executionPolicy?: ExecutionPolicy;
  settings?: Settings;
  store?: StateStore;
  spec?: AgentSpec;
  runId?: string;
  messages?: Message[];
  runtimeEvents?: RuntimeEvent[];
  fileReadState?: FileReadState;
  mcpProviders?: McpProvider[];
  lspProvider?: LspProvider;
  activeWorktreeSession?: Record<string, unknown>;
  agentRunner?: AgentRunner;
  teams?: Record<string, unknown>;
  teamMessages?: Record<string, unknown>[];
  taskRunner?: {
    run(taskId: string): Promise<unknown>;
    cancel(taskId: string): Promise<unknown>;
  };
  sleepWake?: SleepWakeContext;
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
  listResources?: () => Promise<unknown[]>;
  list_resources?: () => Promise<unknown[]>;
  readResource?: (uri: string) => Promise<unknown>;
  read_resource?: (uri: string) => Promise<unknown>;
  listPrompts?: () => Promise<unknown[]>;
  list_prompts?: () => Promise<unknown[]>;
  getPrompt?: (name: string, args: Record<string, unknown>) => Promise<unknown>;
  get_prompt?: (name: string, args: Record<string, unknown>) => Promise<unknown>;
  close?: () => Promise<void>;
};

export type ToolExecution = {
  events: RuntimeEvent[];
  result: ToolResult;
};

export type ToolHandler = (context: ToolExecutionContext, args: JsonObject) => Promise<unknown>;

export type ToolDefinition = {
  name: string;
  description: string;
  risk: "low" | "medium" | "high";
  parameters: Record<string, unknown>;
  handler: ToolHandler;
};

export type ToolFailure = {
  message: string;
};
