import type { Message } from "../types/runtimeTypes.js";
import type { ModelToolDefinition, ModelTurn } from "../types/modelTypes.js";
import type { ModelClientConfig, TextDeltaHandler } from "./modelClientTypes.js";
import { messagesTextStream } from "./modelTextStreams.js";
import { postJson, streamSse } from "./modelHttp.js";
import { claudeMessagesRequestBody, parseClaudeMessagesTurn } from "./anthropicProtocolPayloads.js";

export async function claudeComplete(config: ModelClientConfig, messages: Message[], tools: ModelToolDefinition[] = []): Promise<ModelTurn> {
  return parseClaudeMessagesTurn(await postJson(config, "/messages", claudeMessagesRequestBody(config, messages, tools)));
}

export async function claudeStream(config: ModelClientConfig, messages: Message[], onDelta: TextDeltaHandler): Promise<string> {
  const body = { ...claudeMessagesRequestBody(config, messages), stream: true };
  return streamSse(config, "/messages", body, messagesTextStream(), onDelta);
}
