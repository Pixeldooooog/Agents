import { safeName } from "../tools/promptTools.js";
import type { ToolExecutionContext } from "../tools/toolContracts.js";
import type { JsonObject } from "../types/jsonTypes.js";
import { executeWorkflowPlan } from "./workflowExecution.js";
import { boundedLimit, nodePayload, validateWorkflow, workflowHaystack, workflowPayload, workflowPlan } from "./workflowModels.js";
import { deleteSavedWorkflow, listSavedWorkflows, readSavedWorkflow, saveWorkflowTemplate } from "./workflowTemplates.js";

export async function handleWorkflowTemplates(context: ToolExecutionContext, args: JsonObject): Promise<Record<string, unknown>> {
  let workflows = await listSavedWorkflows(context);
  const query = String(args.query || "").trim().toLowerCase();
  if (query) workflows = workflows.filter((workflow) => workflowHaystack(workflow).includes(query));
  const limit = boundedLimit(args.max_results, 50);
  return { workflows: workflows.slice(0, limit), count: Math.min(workflows.length, limit), total: workflows.length };
}

export async function handleWorkflowRead(context: ToolExecutionContext, args: JsonObject): Promise<Record<string, unknown>> {
  return readSavedWorkflow(context, safeName(args.name, "workflow"));
}

export async function handleWorkflowSave(context: ToolExecutionContext, args: JsonObject): Promise<Record<string, unknown>> {
  const name = safeName(args.name, "workflow");
  return saveWorkflowTemplate(context, name, workflowPlan(args, name), Boolean(args.overwrite));
}

export async function handleWorkflowDelete(context: ToolExecutionContext, args: JsonObject): Promise<Record<string, unknown>> {
  return deleteSavedWorkflow(context, safeName(args.name, "workflow"));
}

export async function handleWorkflowValidate(_context: ToolExecutionContext, args: JsonObject): Promise<Record<string, unknown>> {
  const plan = workflowPlan(args, String(args.workflow_id || "workflow"));
  const orderedNodes = validateWorkflow(plan);
  return {
    workflow: workflowPayload(plan),
    order: orderedNodes.map((node) => node.node_id),
    nodes: orderedNodes.map(nodePayload)
  };
}

export async function handleWorkflowRun(context: ToolExecutionContext, args: JsonObject): Promise<Record<string, unknown>> {
  const plan = workflowPlan(args, String(args.workflow_id || "workflow"));
  const orderedNodes = validateWorkflow(plan);
  return executeWorkflowPlan(context, plan, orderedNodes, args.stop_on_error !== false);
}

export async function handleWorkflowRunSaved(context: ToolExecutionContext, args: JsonObject): Promise<Record<string, unknown>> {
  const readResult = await handleWorkflowRead(context, { name: args.name });
  const workflow = readResult.workflow as Record<string, unknown>;
  const runResult = await handleWorkflowRun(context, { ...workflow, stop_on_error: args.stop_on_error });
  return { name: readResult.name, path: readResult.path, ...runResult };
}
