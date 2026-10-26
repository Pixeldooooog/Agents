import type { Settings } from "../config/settings.js";
import { defaultEnabledTools } from "../models/modelProfiles.js";
import { builtinToolNames, canonicalToolName } from "../tools/toolRegistry.js";
import type { AgentSpec } from "../types/agentTypes.js";

/** Authorization fields of a spec, copied so later mutation of the spec cannot change them. */
export type ToolAuthorization = Readonly<{
  permissionProfile: string;
  enabledTools: readonly string[];
  deniedTools: readonly string[];
  approvalRequiredTools: readonly string[];
}>;

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

export function isToolEnabled(start: ToolAuthorization, settings: Settings, spec: AgentSpec, toolName: string): boolean {
  return enabledBy(start, toolName) && enabledBy(toolAuthorizationSnapshot(settings, spec), toolName);
}

export function deniesTool(start: ToolAuthorization, settings: Settings, spec: AgentSpec, toolName: string): boolean {
  return deniedBy(start, toolName) || deniedBy(toolAuthorizationSnapshot(settings, spec), toolName);
}

/** Callers check deniesTool first; a denied tool is never offered for approval. */
export function requiresApproval(start: ToolAuthorization, settings: Settings, spec: AgentSpec, toolName: string): boolean {
  return approvalRequiredBy(start, toolName) || approvalRequiredBy(toolAuthorizationSnapshot(settings, spec), toolName);
}

function enabledBy(authorization: ToolAuthorization, toolName: string): boolean {
  return authorization.enabledTools.includes(canonicalToolName(toolName));
}

function deniedBy(authorization: ToolAuthorization, toolName: string): boolean {
  return authorization.permissionProfile === "deny" || authorization.deniedTools.includes(canonicalToolName(toolName));
}

function approvalRequiredBy(authorization: ToolAuthorization, toolName: string): boolean {
  if (/^mcp_[a-f0-9]{56}$/.test(toolName) || ["hook.add", "hook.delete"].includes(toolName)) return true;
  return authorization.permissionProfile === "ask" || authorization.approvalRequiredTools.includes(canonicalToolName(toolName));
}

function effectiveEnabledTools(settings: Settings, spec: AgentSpec): string[] {
  const configured = spec.enabled_tools.length ? spec.enabled_tools : defaultEnabledTools(settings);
  return configured.length ? configured : builtinToolNames;
}
