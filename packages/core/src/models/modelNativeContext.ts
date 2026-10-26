import type { Message } from "../types/runtimeTypes.js";
import type { ModelNativeContext } from "../types/modelTypes.js";
import type { ModelClientConfig } from "./modelClientTypes.js";
import { requireRecord } from "./modelProtocolValidation.js";

export function nativeContext(config: ModelClientConfig, protocol: ModelNativeContext["protocol"], items: unknown[]): ModelNativeContext {
  return { protocol, model: config.model, baseUrl: config.baseUrl, items: items.map(item => structuredClone(requireRecord(item, "native context item"))) };
}

/** Only replay provider-private state to the exact model and endpoint that produced it. */
export function replayNativeContext(message: Message, config: ModelClientConfig | undefined, protocol: ModelNativeContext["protocol"]): Record<string, unknown>[] | undefined {
  const context = message.model_context;
  if (message.role !== "assistant" || !context || !config) return;
  if (context.protocol !== protocol || context.model !== config.model || context.baseUrl !== config.baseUrl) return;
  return structuredClone(context.items);
}
