import { ModelConfigError } from "./modelErrors.js";
import type { ModelProtocol } from "./modelClientTypes.js";
import type { AgentSpec } from "../types/agentTypes.js";
import type { ModelProfile } from "../types/modelTypes.js";
import type { Settings } from "../config/settings.js";

const protocolAliases: Record<ModelProtocol, string[]> = {
  "openai-chat": ["openai", "chat", "openai-chat-completions", "chat-completions"],
  "openai-responses": ["responses", "response"],
  "claude-messages": ["anthropic", "claude"],
  gemini: ["google", "gemini-generate-content"]
};

const defaultBaseUrls: Record<ModelProtocol, string> = {
  "openai-chat": "https://api.openai.com/v1",
  "openai-responses": "https://api.openai.com/v1",
  "claude-messages": "https://api.anthropic.com/v1",
  gemini: "https://generativelanguage.googleapis.com/v1beta"
};

export function normalizeProtocol(value: string): ModelProtocol {
  const normalized = String(value || "").trim().toLowerCase();
  for (const standard of Object.keys(protocolAliases) as ModelProtocol[]) {
    const aliases = protocolAliases[standard];
    if (normalized === standard || aliases.includes(normalized)) return standard;
  }
  if (!normalized) return "openai-chat";
  throw new ModelConfigError(`unsupported model protocol: ${normalized}`);
}

export function defaultBaseUrl(protocol: string): string {
  return defaultBaseUrls[normalizeProtocol(protocol)] || defaultBaseUrls["openai-chat"];
}

export function normalizeBaseUrl(protocol: string, baseUrl: string): string {
  let normalized = String(baseUrl || defaultBaseUrl(protocol)).replace(/\/$/, "");
  for (const suffix of ["/chat/completions", "/responses", "/messages"]) {
    if (normalized.endsWith(suffix)) normalized = normalized.slice(0, -suffix.length);
  }
  return normalized.replace(/\/$/, "");
}

export function buildModelProfiles(settings: Settings): ModelProfile[] {
  const profiles: ModelProfile[] = [
    profile("openai", "openai-chat", settings.models.openai, "env"),
    profile("responses", "openai-responses", settings.models.openai_responses, "env"),
    profile("claude", "claude-messages", prefer(settings.agent.claude, settings.models.anthropic), "env"),
    profile("gemini", "gemini", settings.models.gemini, "env")
  ];
  return profiles.filter((item, index, all) => {
    const key = `${item.protocol}:${item.model}:${item.base_url}`;
    return all.findIndex((candidate) => `${candidate.protocol}:${candidate.model}:${candidate.base_url}` === key) === index;
  });
}

export function activeProfileName(profiles: ModelProfile[], spec: AgentSpec): string {
  const protocol = normalizeProtocol(spec.protocol);
  const baseUrl = normalizeBaseUrl(protocol, spec.base_url);
  const found = profiles.find((item) => item.protocol === protocol && item.model === spec.model && normalizeBaseUrl(protocol, item.base_url) === baseUrl);
  return found?.name || "";
}

export function profileDefaults(settings: Settings): Partial<AgentSpec> {
  const protocol = normalizeProtocol(settings.agent.protocol);
  const modelGroup = groupForProtocol(settings, protocol);
  return {
    protocol,
    model: modelGroup.model,
    base_url: modelGroup.baseUrl || defaultBaseUrl(protocol),
    api_key: modelGroup.apiKey,
    system_prompt: settings.agent.systemPrompt,
    enabled_tools: defaultEnabledTools(settings)
  };
}

export function defaultEnabledTools(settings: Settings): string[] {
  return settings.agent.enabledTools.length ? settings.agent.enabledTools : settings.agent.builtinTools;
}

function profile(name: string, protocol: string, values: { apiKey: string; baseUrl: string; model: string }, source: string): ModelProfile {
  const normalized = normalizeProtocol(protocol);
  const baseUrl = normalizeBaseUrl(normalized, values.baseUrl);
  return {
    name,
    protocol: normalized,
    model: values.model,
    base_url: baseUrl,
    endpoint: endpointFor(normalized, baseUrl, values.model),
    aliases: protocolAliases[normalized] || [],
    source,
    configured: Boolean(values.apiKey && values.model)
  };
}

function groupForProtocol(settings: Settings, protocol: string) {
  if (protocol === "claude-messages") return prefer(settings.agent.claude, settings.models.anthropic);
  if (protocol === "gemini") return settings.models.gemini;
  if (protocol === "openai-responses") return prefer(settings.models.openai_responses, settings.models.openai);
  return settings.models.openai;
}

function prefer(primary: { apiKey: string; baseUrl: string; model: string }, fallback: { apiKey: string; baseUrl: string; model: string }) {
  return {
    apiKey: primary.apiKey || fallback.apiKey,
    baseUrl: primary.baseUrl || fallback.baseUrl,
    model: primary.model || fallback.model
  };
}

function endpointFor(protocol: string, baseUrl: string, model: string): string {
  if (protocol === "openai-chat") return `${baseUrl}/chat/completions`;
  if (protocol === "openai-responses") return `${baseUrl}/responses`;
  if (protocol === "claude-messages") return `${baseUrl}/messages`;
  if (protocol === "gemini") return `${baseUrl}/models/${encodeURIComponent(model)}:generateContent`;
  return baseUrl;
}
