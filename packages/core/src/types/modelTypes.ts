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
