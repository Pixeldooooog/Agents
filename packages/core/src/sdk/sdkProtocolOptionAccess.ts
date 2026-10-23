import type { StoreScopeFilter } from "../store/storeFilters.js";
import { canonicalToolName } from "../tools/toolRegistry.js";
import type { SdkProtocolRunnerOptions } from "./sdkProtocolRunner.js";

export function sdkOptionSessionId(options: SdkProtocolRunnerOptions): string {
  return stringOption(options.sessionId ?? options.session_id);
}

export function sdkOptionRunId(options: SdkProtocolRunnerOptions): string {
  return stringOption(options.metadata?.runId ?? options.metadata?.run_id);
}

export function sdkOptionScope(options: SdkProtocolRunnerOptions): StoreScopeFilter {
  return {
    tenant_id: stringOption(options.tenantId ?? options.tenant_id),
    user_id: stringOption(options.userId ?? options.user_id),
    agent_id: stringOption(options.agentId ?? options.agent_id),
    workspace_id: stringOption(options.workspaceId ?? options.workspace_id)
  };
}

export function sdkOptionPermissionProfile(options: SdkProtocolRunnerOptions): string {
  return stringOption(options.permissionProfile ?? options.permission_profile) || "ask";
}

export function sdkOptionDeniedTools(options: SdkProtocolRunnerOptions): string[] {
  return canonicalToolNames(options.deniedTools ?? options.denied_tools);
}

export function sdkOptionApprovalRequiredTools(options: SdkProtocolRunnerOptions): string[] {
  return canonicalToolNames(options.approvalRequiredTools ?? options.approval_required_tools);
}

export function sdkOptionEnabledTools(options: SdkProtocolRunnerOptions): string[] | undefined {
  const value = options.enabledTools ?? options.enabled_tools;
  return value === undefined ? undefined : stringListOption(value);
}

function canonicalToolNames(value: unknown): string[] {
  return stringListOption(value).map(canonicalToolName);
}

function stringListOption(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => String(item).trim()).filter(Boolean);
  if (typeof value === "string") return value.split(",").map((item) => item.trim()).filter(Boolean);
  return [];
}

function stringOption(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}
