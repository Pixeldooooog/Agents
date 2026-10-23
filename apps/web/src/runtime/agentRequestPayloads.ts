import type { AgentChatPayload, PermissionMode } from "../types/runtimeTypes";
import { compact } from "./sessionUtils";

type AgentChatPayloadOptions = {
  message: string;
  protocol: string;
  model: string;
  modelBaseUrl: string;
  apiKey: string;
  systemPrompt: string;
  enabledTools: string[];
  permissionMode: PermissionMode;
  tenantId: string;
  userId: string;
  agentId: string;
  workspaceId: string;
};

type AgentScopeFilterOptions = {
  tenantId: string;
  userId: string;
  agentId: string;
};

export function buildAgentChatPayload(options: AgentChatPayloadOptions): AgentChatPayload {
  return compact({
    message: options.message,
    protocol: options.protocol,
    model: options.model,
    base_url: options.modelBaseUrl,
    api_key: options.apiKey,
    system_prompt: options.systemPrompt,
    enabled_tools: options.enabledTools,
    permission_profile: options.permissionMode,
    tenant_id: options.tenantId,
    user_id: options.userId,
    agent_id: options.agentId,
    workspace_id: options.workspaceId
  }) as AgentChatPayload;
}

export function buildAgentScopeFilter(options: AgentScopeFilterOptions): Record<string, string> {
  return compact({
    tenant_id: options.tenantId,
    user_id: options.userId,
    agent_id: options.agentId
  }) as Record<string, string>;
}
