import type { Settings } from "../config/settings.js";
import type { JsonStateStore } from "../store/jsonStateStore.js";
import type { AgentSpec } from "../types/agentTypes.js";
import type { Message, RuntimeEvent } from "../types/runtimeTypes.js";
import type { FileReadState, ToolExecutionContext } from "../tools/toolContracts.js";

export type RuntimeOptions = {
  settings: Settings;
  store?: JsonStateStore;
  taskRunner?: ToolExecutionContext["taskRunner"];
  mcpProviders?: ToolExecutionContext["mcpProviders"];
  lspProvider?: ToolExecutionContext["lspProvider"];
  agentRunner?: ToolExecutionContext["agentRunner"];
  stream?: boolean;
  signal?: AbortSignal;
  fileReadState?: FileReadState;
  sleepWake?: ToolExecutionContext["sleepWake"];
  onEvent?: (event: RuntimeEvent) => void | Promise<void>;
};

export type RuntimeToolContextInput = {
  spec: AgentSpec;
  runId: string;
  messages: Message[];
  runtimeEvents: RuntimeEvent[];
};

export function runtimeToolExecutionContext(
  options: RuntimeOptions,
  input: RuntimeToolContextInput
): Partial<ToolExecutionContext> {
  return {
    settings: options.settings,
    store: options.store,
    spec: input.spec,
    runId: input.runId,
    messages: input.messages,
    runtimeEvents: input.runtimeEvents,
    fileReadState: options.fileReadState,
    sleepWake: options.sleepWake,
    mcpProviders: options.mcpProviders,
    lspProvider: options.lspProvider,
    agentRunner: options.agentRunner,
    taskRunner: options.taskRunner
  };
}
