import type { JsonObject } from "../types/jsonTypes.js";
import type { AgentSpec } from "../types/agentTypes.js";
import { optionalPermissionBehavior, permissionBehaviorFromValue } from "../permissions/permissionBehaviors.js";
import { permissionExplanation } from "../permissions/permissionDecisions.js";
import { permissionSourcesPayload, permissionStatusPayload } from "../permissions/permissionPayloads.js";
import { addPermissionRule, removePermissionRules } from "../permissions/permissionRuleSets.js";
import { defineTool, type RegisteredTool, type ToolContext } from "./toolContracts.js";
import {
  permissionAddRuleSchema,
  permissionExplainSchema,
  permissionRemoveRuleSchema,
  permissionStatusSchema
} from "./permissionToolSchemas.js";

export const permissionToolDefinitions: RegisteredTool[] = [
  defineTool({
    name: "permission.status",
    description: "Read current tool permission profile and configured approval/deny lists.",
    risk: "low",
    parameters: permissionStatusSchema,
    requires: [],
    handler: permissionStatus
  }),
  defineTool({
    name: "permission.sources",
    description: "Read tool permission rules grouped by source and behavior.",
    risk: "low",
    parameters: permissionStatusSchema,
    requires: [],
    handler: permissionSources
  }),
  defineTool({
    name: "permission.explain",
    description: "Explain the permission decision and impact for a hypothetical tool call.",
    risk: "low",
    parameters: permissionExplainSchema,
    requires: [],
    handler: permissionExplain
  }),
  defineTool({
    name: "permission.add_rule",
    description: "Add a session-scoped allow, deny, or ask rule for a tool.",
    risk: "medium",
    parameters: permissionAddRuleSchema,
    requires: [],
    handler: permissionAddRule
  }),
  defineTool({
    name: "permission.remove_rule",
    description: "Remove session-scoped permission rules for a tool.",
    risk: "medium",
    parameters: permissionRemoveRuleSchema,
    requires: [],
    handler: permissionRemoveRule
  })
];

async function permissionStatus(context: ToolContext): Promise<Record<string, unknown>> {
  return permissionStatusPayload(requiredSpec(context));
}

async function permissionSources(context: ToolContext): Promise<Record<string, unknown>> {
  return permissionSourcesPayload(requiredSpec(context));
}

async function permissionExplain(context: ToolContext, args: JsonObject): Promise<Record<string, unknown>> {
  const tool = requiredText(args.tool, "tool");
  return permissionExplanation(requiredSpec(context), tool, args.arguments);
}

async function permissionAddRule(context: ToolContext, args: JsonObject): Promise<Record<string, unknown>> {
  const spec = requiredSpec(context);
  const behavior = permissionBehaviorFromValue(args.behavior);
  const tool = requiredText(args.tool, "tool");
  const added = addPermissionRule(spec, behavior, tool);
  return { added, status: permissionStatusPayload(spec) };
}

async function permissionRemoveRule(context: ToolContext, args: JsonObject): Promise<Record<string, unknown>> {
  const spec = requiredSpec(context);
  const tool = requiredText(args.tool, "tool");
  const removed = removePermissionRules(spec, optionalPermissionBehavior(args.behavior), tool);
  return { removed, status: permissionStatusPayload(spec) };
}

function requiredSpec(context: ToolContext): AgentSpec {
  if (!context.spec) throw new Error("agent spec is not available");
  return context.spec;
}

function requiredText(value: unknown, name: string): string {
  const text = String(value || "").trim();
  if (!text) throw new Error(`${name} is required`);
  return text;
}
