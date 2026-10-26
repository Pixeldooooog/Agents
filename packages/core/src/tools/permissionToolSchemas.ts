import { permissionRuleBehaviorValues } from "../permissions/permissionBehaviors.js";

export const permissionStatusSchema = {
  type: "object",
  properties: {}
};

export const permissionExplainSchema = {
  type: "object",
  properties: {
    tool: { type: "string", description: "Tool name to check." },
    arguments: { type: "object", additionalProperties: true }
  },
  required: ["tool"]
};

export const permissionAddRuleSchema = {
  type: "object",
  properties: {
    behavior: { type: "string", enum: permissionRuleBehaviorValues, description: "Rules can only tighten permissions during a run." },
    tool: { type: "string", description: "Tool name, wildcard, or command rule such as shell.run(git:*)." }
  },
  required: ["behavior", "tool"]
};

