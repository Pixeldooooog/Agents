import type { ModelStreamHandler, ModelToolDefinition, ModelTurn } from "../types/modelTypes.js";
import type { Message } from "../types/runtimeTypes.js";
import type { ModelClientConfig } from "./modelClientTypes.js";
import { ModelConfigError, ModelProtocolError } from "./modelErrors.js";
import { normalizeProtocol } from "./modelProfiles.js";
import { postSse } from "./modelHttp.js";
import { openAIChatRequestBody, responsesRequestBody } from "./openaiProtocolPayloads.js";
import { claudeMessagesRequestBody } from "./anthropicProtocolPayloads.js";
import { chatTurnStream } from "./chatTurnStream.js";
import { responsesTurnStream } from "./responsesTurnStream.js";
import { messagesTurnStream } from "./messagesTurnStream.js";

export async function streamModelTurn(
  config: ModelClientConfig,
  messages: Message[],
  tools: ModelToolDefinition[],
  onEvent: ModelStreamHandler
): Promise<ModelTurn> {
  const resolved = { ...config, protocol: normalizeProtocol(config.protocol) };
  if (resolved.protocol === "gemini") throw new ModelConfigError("Gemini model-turn streaming is not implemented");
  const request = resolved.protocol === "openai-chat"
    ? { path: "/chat/completions", body: { ...openAIChatRequestBody(resolved, messages, tools), stream_options: { include_usage: true } }, decode: chatTurnStream() }
    : resolved.protocol === "openai-responses"
      ? { path: "/responses", body: responsesRequestBody(resolved, messages, tools), decode: responsesTurnStream(resolved) }
      : { path: "/messages", body: claudeMessagesRequestBody(resolved, messages, tools), decode: messagesTurnStream(resolved) };
  for await (const event of postSse(resolved, request.path, { ...request.body, stream: true })) {
    const step = request.decode(event);
    for (const delta of step.events) {
      await onEvent(delta);
      config.signal?.throwIfAborted();
    }
    if (step.turn) {
      if (step.turn.usage) await onEvent({ type: "usage", usage: step.turn.usage });
      config.signal?.throwIfAborted();
      await onEvent({ type: "completed", turn: step.turn });
      config.signal?.throwIfAborted();
      return step.turn;
    }
  }
  throw new ModelProtocolError("model stream ended before protocol completion");
}
