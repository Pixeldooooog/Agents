import type { AgentSpec } from "../types/agentTypes.js";
import type { PermissionRuleBehavior } from "./permissionBehaviors.js";

export type PermissionRule = {
  source: "agent_spec";
  behavior: "deny" | "ask";
  tool: string;
};

/** Adds a stricter rule. Deny supersedes ask; asking for an already denied tool leaves it denied. */
export function addPermissionRule(spec: AgentSpec, behavior: PermissionRuleBehavior, tool: string): Record<string, string> {
  if (behavior === "deny") {
    spec.denied_tools = addUnique(spec.denied_tools, tool);
    spec.approval_required_tools = removeValue(spec.approval_required_tools, tool);
    return { behavior, tool };
  }
  if (spec.denied_tools.includes(tool)) return { behavior: "deny", tool };
  spec.approval_required_tools = addUnique(spec.approval_required_tools, tool);
  return { behavior, tool };
}

export function permissionRules(spec: AgentSpec): PermissionRule[] {
  return [
    ...spec.denied_tools.map((tool) => ({ source: "agent_spec" as const, behavior: "deny" as const, tool })),
    ...spec.approval_required_tools.map((tool) => ({ source: "agent_spec" as const, behavior: "ask" as const, tool }))
  ];
}

export function permissionRulesBySource(spec: AgentSpec): Record<string, Record<string, string[]>> {
  return {
    agent_spec: {
      deny: [...spec.denied_tools],
      ask: [...spec.approval_required_tools],
      allow: []
    }
  };
}

function addUnique(items: string[], value: string): string[] {
  return items.includes(value) ? items : [...items, value];
}

function removeValue(items: string[], value: string): string[] {
  return items.filter((item) => item !== value);
}
