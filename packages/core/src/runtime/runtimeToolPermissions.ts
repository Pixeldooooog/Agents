import type { Settings } from "../config/settings.js";
import { defaultEnabledTools } from "../models/modelProfiles.js";
import { builtinToolNames, canonicalToolName } from "../tools/toolRegistry.js";
import type { AgentSpec } from "../types/agentTypes.js";

import { permissionDecision, type ToolAuthorization } from "../permissions/permissionDecisions.js";
export type { ToolAuthorization } from "../permissions/permissionDecisions.js";

/**
 * Taken when a run (or resumed run) starts. Tools receive the live spec and may rewrite it, so every gate
 * combines this snapshot with the current spec: a tool can tighten authorization within a run, never loosen it.
 */
export function toolAuthorizationSnapshot(settings: Settings, spec: AgentSpec): ToolAuthorization {
  return Object.freeze({
    permissionProfile: spec.permission_profile,
    enabledTools: Object.freeze(effectiveEnabledTools(settings, spec).map(canonicalToolName)),
    deniedTools: Object.freeze(spec.denied_tools.map(canonicalToolName)),
    approvalRequiredTools: Object.freeze(spec.approval_required_tools.map(canonicalToolName))
  });
}

export function runtimePermissionDecision(start: ToolAuthorization, settings: Settings, spec: AgentSpec, toolName: string) {
  return permissionDecision(start, toolAuthorizationSnapshot(settings, spec), canonicalToolName(toolName));
}

export function isToolEnabled(start: ToolAuthorization, settings: Settings, spec: AgentSpec, toolName: string): boolean {
  const name = canonicalToolName(toolName);
  return start.enabledTools.includes(name) && toolAuthorizationSnapshot(settings, spec).enabledTools.includes(name);
}

export function deniesTool(start: ToolAuthorization, settings: Settings, spec: AgentSpec, toolName: string): boolean {
  return runtimePermissionDecision(start, settings, spec, toolName).behavior === "deny";
}

export function requiresApproval(start: ToolAuthorization, settings: Settings, spec: AgentSpec, toolName: string): boolean {
  return runtimePermissionDecision(start, settings, spec, toolName).behavior === "ask";
}

function effectiveEnabledTools(settings: Settings, spec: AgentSpec): string[] {
  const configured = spec.enabled_tools.length ? spec.enabled_tools : defaultEnabledTools(settings);
  return configured.length ? configured : builtinToolNames;
}
