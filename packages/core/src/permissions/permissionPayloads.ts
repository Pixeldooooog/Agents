import type { AgentSpec } from "../types/agentTypes.js";
import { permissionRules, permissionRulesBySource } from "./permissionRuleSets.js";

export function permissionStatusPayload(spec: AgentSpec): Record<string, unknown> {
  return {
    profile: spec.permission_profile || "auto",
    permission_profile: spec.permission_profile || "auto",
    allowed_tools: [],
    restrict_allowed_tools: false,
    denied_tools: [...spec.denied_tools],
    approval_required_tools: [...spec.approval_required_tools],
    enabled_tools: [...spec.enabled_tools],
    runtime_policy: "",
    rules_by_source: permissionRulesBySource(spec)
  };
}

export function permissionSourcesPayload(spec: AgentSpec): Record<string, unknown> {
  const status = permissionStatusPayload(spec);
  return {
    mode: status.profile,
    permission_profile: status.permission_profile,
    rules: permissionRules(spec),
    rules_by_source: status.rules_by_source,
    restrict_allowed_tools: false,
    runtime_policy: "",
    settings: [],
    enabled_tools: status.enabled_tools
  };
}
