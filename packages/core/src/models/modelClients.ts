import type { AgentSpec } from "../types/agentTypes.js";
import type { Message } from "../types/runtimeTypes.js";
import type { ModelToolDefinition, ModelTurn } from "../types/modelTypes.js";
import type { Settings } from "../config/settings.js";
import type { ModelClientConfig, TextDeltaHandler } from "./modelClientTypes.js";
import { defaultBaseUrl, normalizeBaseUrl, normalizeProtocol } from "./modelProfiles.js";
import { claudeComplete } from "./anthropicModelClient.js";
import { geminiComplete } from "./geminiModelClient.js";
import { openAIChatComplete, openAIChatStream, responsesComplete, responsesStream } from "./openaiModelClient.js";

export class ModelConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ModelConfigError";
  }
}

export type { ModelClientConfig, TextDeltaHandler } from "./modelClientTypes.js";

export function resolveModelClientConfig(settings: Settings, spec: AgentSpec): ModelClientConfig {
  const protocol = normalizeProtocol(spec.protocol || settings.agent.protocol);
  const configured = configuredFor(settings, protocol);
  const model = spec.model || configured.model;
  const apiKey = spec.api_key || configured.apiKey;
  const baseUrl = normalizeBaseUrl(protocol, spec.base_url || configured.baseUrl || defaultBaseUrl(protocol));
  const missing = [!apiKey && "API_KEY", !model && "MODEL"].filter(Boolean);
  if (missing.length) throw new ModelConfigError(`missing agent model configuration: ${missing.join(", ")}`);
  return {
    protocol,
    model,
    apiKey,
    baseUrl,
    maxTokens: settings.agent.maxTokens,
    maxThinkingTokens: spec.runtime.maxThinkingTokens,
    timeoutMs: Math.max(1, settings.agent.timeout) * 1000
  };
}

export async function completeText(config: ModelClientConfig, messages: Message[]): Promise<string> {
  return (await completeModelTurn(config, messages)).content;
}

export async function completeModelTurn(config: ModelClientConfig, messages: Message[], tools: ModelToolDefinition[] = []): Promise<ModelTurn> {
  if (config.protocol === "claude-messages") return claudeComplete(config, messages, tools);
  if (config.protocol === "gemini") return geminiComplete(config, messages);
  if (config.protocol === "openai-responses") return responsesComplete(config, messages, tools);
  return openAIChatComplete(config, messages, tools);
}

export async function streamText(config: ModelClientConfig, messages: Message[], onDelta: TextDeltaHandler): Promise<string> {
  if (config.protocol === "openai-chat") return openAIChatStream(config, messages, onDelta);
  if (config.protocol === "openai-responses") return responsesStream(config, messages, onDelta);
  const text = await completeText(config, messages);
  if (text) onDelta(text);
  return text;
}

function configuredFor(settings: Settings, protocol: string) {
  if (protocol === "claude-messages") return prefer(settings.agent.claude, settings.models.anthropic);
  if (protocol === "gemini") return settings.models.gemini;
  if (protocol === "openai-responses") return prefer(settings.models.openai_responses, settings.models.openai);
  return settings.models.openai;
}

function prefer(
  primary: { apiKey: string; baseUrl: string; model: string },
  fallback: { apiKey: string; baseUrl: string; model: string }
) {
  return {
    apiKey: primary.apiKey || fallback.apiKey,
    baseUrl: primary.baseUrl || fallback.baseUrl,
    model: primary.model || fallback.model
  };
}
