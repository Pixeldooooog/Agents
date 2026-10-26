import type { Settings } from "../config/settings.js";
import { defaultEnabledTools } from "../models/modelProfiles.js";
import { builtinToolNames, canonicalToolName } from "../tools/toolRegistry.js";
import type { AgentSpec } from "../types/agentTypes.js";

export function deniesTool(spec: AgentSpec, toolName: string): boolean {
  return spec.permission_profile === "deny" || spec.denied_tools.some(name => canonicalToolName(name) === canonicalToolName(toolName));
}

export function requiresApproval(spec: AgentSpec, toolName: string): boolean {
  if (spec.permission_profile === "deny") return false;
  if (/^mcp_[a-f0-9]{56}$/.test(toolName) || ["hook.add", "hook.delete"].includes(toolName)) return true;
  return spec.approval_required_tools.some(name => canonicalToolName(name) === canonicalToolName(toolName)) || spec.permission_profile === "ask";
}

export function isToolEnabled(settings: Settings, spec: AgentSpec, toolName: string): boolean {
  const configured = spec.enabled_tools.length ? spec.enabled_tools : defaultEnabledTools(settings);
  const enabled = configured.length ? configured : builtinToolNames;
  return enabled.some(name => canonicalToolName(name) === canonicalToolName(toolName));
}
