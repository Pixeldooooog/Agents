import type { AgentSpec } from "../types/agentTypes.js";

const writeOrExecuteTools = new Set(["filesystem.write", "patch.apply", "shell.run", "git.commit"]);

export function permissionExplanation(spec: AgentSpec, tool: string, args: unknown): Record<string, unknown> {
  const decision = permissionDecision(spec, tool);
  return {
    tool,
    arguments: args && typeof args === "object" ? args : {},
    decision,
    impact: {
      tool,
      risk: decision.behavior === "deny" ? "blocked" : writeOrExecuteTools.has(tool) ? "writes_or_executes" : "read_or_state"
    }
  };
}

export function permissionDecision(spec: Pick<AgentSpec, "permission_profile" | "denied_tools" | "approval_required_tools">, tool: string): Record<string, string> {
  if (spec.permission_profile === "deny" || spec.denied_tools.includes(tool)) return { behavior: "deny", reason: "tool is denied" };
  if (spec.permission_profile === "ask" || spec.approval_required_tools.includes(tool)) return { behavior: "ask", reason: "tool requires approval" };
  return { behavior: "allow", reason: "tool is allowed" };
}
