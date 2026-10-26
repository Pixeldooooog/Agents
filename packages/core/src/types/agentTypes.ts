export type AgentSpec = {
  protocol: string;
  model: string;
  base_url: string;
  api_key: string;
  system_prompt: string;
  enabled_tools: string[];
  permission_profile: "auto" | "ask" | "deny" | string;
  approval_required_tools: string[];
  denied_tools: string[];
  tenant_id: string;
  user_id: string;
  agent_id: string;
  workspace_id: string;
  runtime: AgentRuntimeConfig;
  metadata: Record<string, string>;
};

export type AgentRuntimeConfig = {
  maxToolIterations?: number;
  maxThinkingTokens?: number;
};

export type PublicAgentSpec = Omit<AgentSpec, "api_key"> & { api_key?: never };

export type AgentChatPayload = Partial<Omit<AgentSpec, "metadata" | "runtime">> & {
  message: string;
  previous_run_id?: string;
  runtime?: Partial<AgentRuntimeConfig>;
  metadata?: Record<string, string>;
};

export type RunApprovalPayload = {
  approval_id: string;
  approved: boolean;
  decision?: "allow_once" | "allow_for_run" | "deny" | string;
};

export function specFromPayload(payload: Partial<AgentChatPayload>, defaults?: Partial<AgentSpec>): AgentSpec {
  return {
    protocol: stringValue(payload.protocol, defaults?.protocol || "openai-chat"),
    model: stringValue(payload.model, defaults?.model || ""),
    base_url: stringValue(payload.base_url, defaults?.base_url || ""),
    api_key: stringValue(payload.api_key, defaults?.api_key || ""),
    system_prompt: stringValue(payload.system_prompt, defaults?.system_prompt || ""),
    enabled_tools: stringList(payload.enabled_tools ?? defaults?.enabled_tools),
    permission_profile: stringValue(payload.permission_profile, defaults?.permission_profile || "ask"),
    approval_required_tools: stringList(payload.approval_required_tools ?? defaults?.approval_required_tools),
    denied_tools: stringList(payload.denied_tools ?? defaults?.denied_tools),
    tenant_id: stringValue(payload.tenant_id, defaults?.tenant_id || ""),
    user_id: stringValue(payload.user_id, defaults?.user_id || ""),
    agent_id: stringValue(payload.agent_id, defaults?.agent_id || ""),
    workspace_id: stringValue(payload.workspace_id, defaults?.workspace_id || ""),
    runtime: runtimeConfig(payload.runtime, defaults?.runtime),
    metadata: { ...(defaults?.metadata || {}), ...(payload.metadata || {}) }
  };
}

export function publicSpec(spec: AgentSpec): PublicAgentSpec {
  const { api_key: _apiKey, ...rest } = spec;
  return { ...rest, enabled_tools: [...rest.enabled_tools], runtime: { ...rest.runtime } };
}

function stringValue(value: unknown, fallback = ""): string {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function stringList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(String).map((item) => item.trim()).filter(Boolean);
  if (typeof value === "string") return value.split(",").map((item) => item.trim()).filter(Boolean);
  return [];
}

function runtimeConfig(payload?: Partial<AgentRuntimeConfig>, defaults?: Partial<AgentRuntimeConfig>): AgentRuntimeConfig {
  const maxToolIterations = nonNegativeInteger(payload?.maxToolIterations)
    ?? nonNegativeInteger(defaults?.maxToolIterations);
  const maxThinkingTokens = nonNegativeInteger(payload?.maxThinkingTokens)
    ?? nonNegativeInteger(defaults?.maxThinkingTokens);
  return {
    ...(maxToolIterations === undefined ? {} : { maxToolIterations }),
    ...(maxThinkingTokens === undefined ? {} : { maxThinkingTokens })
  };
}

function nonNegativeInteger(value: unknown): number | undefined {
  if (value === undefined || value === null || value === "") return undefined;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : undefined;
}
