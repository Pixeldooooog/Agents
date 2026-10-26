import type { JsonObject } from "./jsonTypes.js";
import type { ToolCall } from "./runtimeTypes.js";

export type ModelToolDefinition = {
  name: string;
  description: string;
  parameters: JsonObject;
};

export type ModelTurn = {
  content: string;
  tool_calls: ToolCall[];
  usage?: ModelUsage;
  model_context?: ModelNativeContext;
};

export type ModelUsage = {
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  raw?: JsonObject;
};

export type ModelProfile = {
  name: string;
  protocol: string;
  model: string;
  base_url: string;
  endpoint: string;
  aliases: string[];
  source: string;
  configured: boolean;
};

/** Opaque provider context; runtime persists it but does not interpret it. */
export type ModelNativeContext = {
  protocol: "openai-responses" | "claude-messages";
  model: string;
  baseUrl: string;
  items: JsonObject[];
};

/** Deltas are provisional; only a completed turn may authorize tool execution. */
export type ModelStreamEvent =
  | { type: "text_delta"; delta: string }
  | { type: "tool_call_delta"; index: number; id?: string; name?: string; argumentsDelta?: string }
  | { type: "usage"; usage: ModelUsage }
  | { type: "completed"; turn: ModelTurn };

export type ModelStreamHandler = (event: ModelStreamEvent) => void | Promise<void>;
