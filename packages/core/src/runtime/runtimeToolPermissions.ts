import type { AgentSpec } from "../types/agentTypes.js";

export function deniesTool(spec: AgentSpec, toolName: string): boolean {
  return spec.permission_profile === "deny" || spec.denied_tools.includes(toolName);
}

export function requiresApproval(spec: AgentSpec, toolName: string): boolean {
  if (spec.permission_profile === "deny") return false;
  if (spec.permission_profile === "auto") return false;
  return spec.approval_required_tools.includes(toolName) || spec.permission_profile === "ask";
}
