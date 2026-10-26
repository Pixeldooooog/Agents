import { chatTextStream, responsesTextStream } from "./modelTextStreams.js";
import type { Message } from "../types/runtimeTypes.js";
import type { ModelToolDefinition, ModelTurn } from "../types/modelTypes.js";
import type { ModelClientConfig, TextDeltaHandler } from "./modelClientTypes.js";
import { postJson, streamSse } from "./modelHttp.js";
import {
  openAIChatRequestBody,
  parseOpenAIChatTurn,
  parseResponsesTurn,
  responsesRequestBody
} from "./openaiProtocolPayloads.js";

export async function openAIChatComplete(config: ModelClientConfig, messages: Message[], tools: ModelToolDefinition[] = []): Promise<ModelTurn> {
  return parseOpenAIChatTurn(await postJson(config, "/chat/completions", openAIChatRequestBody(config, messages, tools)));
}

export async function openAIChatStream(config: ModelClientConfig, messages: Message[], onDelta: TextDeltaHandler): Promise<string> {
  const body = { ...openAIChatRequestBody(config, messages), stream: true };
  return streamSse(config, "/chat/completions", body, chatTextStream(), onDelta);
}

export async function responsesComplete(config: ModelClientConfig, messages: Message[], tools: ModelToolDefinition[] = []): Promise<ModelTurn> {
  return parseResponsesTurn(await postJson(config, "/responses", responsesRequestBody(config, messages, tools)));
}

export async function responsesStream(config: ModelClientConfig, messages: Message[], onDelta: TextDeltaHandler): Promise<string> {
  const body = { ...responsesRequestBody(config, messages), stream: true };
  return streamSse(config, "/responses", body, responsesTextStream, onDelta);
}
