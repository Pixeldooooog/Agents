import type { AgentSpec } from "../types/agentTypes.js";
import type { Message } from "../types/runtimeTypes.js";
import type { ModelToolDefinition, ModelTurn } from "../types/modelTypes.js";
import type { Settings } from "../config/settings.js";
import type { ModelClientConfig, TextDeltaHandler } from "./modelClientTypes.js";
import { defaultBaseUrl, normalizeBaseUrl, normalizeProtocol } from "./modelProfiles.js";
import { claudeComplete } from "./anthropicModelClient.js";
import { geminiComplete } from "./geminiModelClient.js";
import { openAIChatComplete, openAIChatStream, responsesComplete, responsesStream } from "./openaiModelClient.js";
import { ModelConfigError } from "./modelErrors.js";

export { ModelConfigError } from "./modelErrors.js";

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
  const resolved = { ...config, protocol: normalizeProtocol(config.protocol) };
  if (resolved.protocol === "gemini" && (tools.length || messages.some(message => message.role === "tool" || message.tool_calls?.length))) {
    throw new ModelConfigError("Gemini tool calling is not implemented; use a text-only request or another protocol");
  }
  switch (resolved.protocol) {
    case "claude-messages": return claudeComplete(resolved, messages, tools);
    case "gemini": return geminiComplete(resolved, messages);
    case "openai-responses": return responsesComplete(resolved, messages, tools);
    case "openai-chat": return openAIChatComplete(resolved, messages, tools);
  }
}

export async function streamText(config: ModelClientConfig, messages: Message[], onDelta: TextDeltaHandler): Promise<string> {
  const resolved = { ...config, protocol: normalizeProtocol(config.protocol) };
  if (resolved.protocol === "openai-chat") return openAIChatStream(resolved, messages, onDelta);
  if (resolved.protocol === "openai-responses") return responsesStream(resolved, messages, onDelta);
  const text = await completeText(resolved, messages);
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
