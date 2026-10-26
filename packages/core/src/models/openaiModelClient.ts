import type { Message } from "../types/runtimeTypes.js";
import type { ModelToolDefinition, ModelTurn } from "../types/modelTypes.js";
import type { ModelClientConfig } from "./modelClientTypes.js";
import { postJson } from "./modelHttp.js";
import {
  openAIChatRequestBody,
  parseOpenAIChatTurn,
  parseResponsesTurn,
  responsesRequestBody
} from "./openaiProtocolPayloads.js";

export async function openAIChatComplete(config: ModelClientConfig, messages: Message[], tools: ModelToolDefinition[] = []): Promise<ModelTurn> {
  return parseOpenAIChatTurn(await postJson(config, "/chat/completions", openAIChatRequestBody(config, messages, tools)));
}

export async function responsesComplete(config: ModelClientConfig, messages: Message[], tools: ModelToolDefinition[] = []): Promise<ModelTurn> {
  return parseResponsesTurn(await postJson(config, "/responses", responsesRequestBody(config, messages, tools)), config);
}
