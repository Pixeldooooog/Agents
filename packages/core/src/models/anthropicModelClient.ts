import type { Message } from "../types/runtimeTypes.js";
import type { ModelToolDefinition, ModelTurn } from "../types/modelTypes.js";
import type { ModelClientConfig } from "./modelClientTypes.js";
import { postJson } from "./modelHttp.js";
import { claudeMessagesRequestBody, parseClaudeMessagesTurn } from "./anthropicProtocolPayloads.js";

export async function claudeComplete(config: ModelClientConfig, messages: Message[], tools: ModelToolDefinition[] = []): Promise<ModelTurn> {
  return parseClaudeMessagesTurn(await postJson(config, "/messages", claudeMessagesRequestBody(config, messages, tools)), config);
}
