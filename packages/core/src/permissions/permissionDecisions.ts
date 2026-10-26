/** Immutable authority at entry, combined with the live policy before each call. */
export type ToolAuthorization = Readonly<{
  permissionProfile: string;
  enabledTools: readonly string[];
  deniedTools: readonly string[];
  approvalRequiredTools: readonly string[];
}>;

export type ToolPermissionDecision = {
  behavior: "allow" | "ask" | "deny";
  reason: string;
};

/** Names and both policies must already be canonicalized by the runtime. */
export function permissionDecision(start: ToolAuthorization, current: ToolAuthorization, tool: string): ToolPermissionDecision {
  for (const policy of [start, current]) {
    if (!policy.enabledTools.includes(tool)) return { behavior: "deny", reason: "tool is not enabled" };
    if (policy.permissionProfile === "deny" || policy.deniedTools.includes(tool)) return { behavior: "deny", reason: "tool is denied" };
  }
  if (/^mcp_[a-f0-9]{56}$/.test(tool) || tool === "hook.add" || tool === "hook.delete") {
    return { behavior: "ask", reason: "external tool or hook configuration requires approval" };
  }
  if ([start, current].some(policy => policy.permissionProfile === "ask" || policy.approvalRequiredTools.includes(tool))) {
    return { behavior: "ask", reason: "tool requires approval" };
  }
  return { behavior: "allow", reason: "tool is allowed" };
}

export function permissionExplanation(decision: ToolPermissionDecision, tool: string, args: unknown): Record<string, unknown> {
  return { tool, arguments: args ?? {}, decision };
}
