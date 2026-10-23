import type { AgentSpec } from "../types/agentTypes.js";
import type { PermissionBehavior } from "./permissionBehaviors.js";

export type PermissionRule = {
  source: "agent_spec";
  behavior: "deny" | "ask";
  tool: string;
};

export function addPermissionRule(spec: AgentSpec, behavior: PermissionBehavior, tool: string): Record<string, string> {
  if (behavior === "allow") {
    spec.denied_tools = removeValue(spec.denied_tools, tool);
    spec.approval_required_tools = removeValue(spec.approval_required_tools, tool);
    if (spec.permission_profile === "deny") spec.permission_profile = "auto";
  } else if (behavior === "deny") {
    spec.denied_tools = addUnique(spec.denied_tools, tool);
    spec.approval_required_tools = removeValue(spec.approval_required_tools, tool);
  } else {
    spec.approval_required_tools = addUnique(spec.approval_required_tools, tool);
    spec.denied_tools = removeValue(spec.denied_tools, tool);
  }
  return { behavior, tool };
}

export function removePermissionRules(spec: AgentSpec, behavior: PermissionBehavior | "", tool: string): Record<string, string>[] {
  const removed: Record<string, string>[] = [];
  if ((!behavior || behavior === "deny") && spec.denied_tools.includes(tool)) {
    spec.denied_tools = removeValue(spec.denied_tools, tool);
    removed.push({ behavior: "deny", tool });
  }
  if ((!behavior || behavior === "ask") && spec.approval_required_tools.includes(tool)) {
    spec.approval_required_tools = removeValue(spec.approval_required_tools, tool);
    removed.push({ behavior: "ask", tool });
  }
  return removed;
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
