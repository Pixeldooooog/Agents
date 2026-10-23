import type { AgentSpec } from "../types/agentTypes.js";
import type { ToolExecutionContext } from "../tools/toolContracts.js";
import { workflowPayload, workflowStatus, type WorkflowNode, type WorkflowPlan } from "./workflowModels.js";

export async function executeWorkflowPlan(context: ToolExecutionContext, plan: WorkflowPlan, orderedNodes: WorkflowNode[], stopOnError: boolean): Promise<Record<string, unknown>> {
  const results = [];
  for (const node of orderedNodes) {
    const result = await runWorkflowNode(context, node);
    results.push(result);
    if (["awaiting_approval", "error"].includes(String(result.status || "")) && stopOnError) {
      return { workflow: workflowPayload(plan), status: result.status, results };
    }
  }
  return { workflow: workflowPayload(plan), status: workflowStatus(results), results };
}

async function runWorkflowNode(context: ToolExecutionContext, node: WorkflowNode): Promise<Record<string, unknown>> {
  if (node.kind === "human_approval") {
    return { node_id: node.node_id, kind: node.kind, name: node.name, status: "awaiting_approval", message: String(node.raw.input || node.raw.prompt || node.name) };
  }

  if (node.kind === "task") {
    const spec = requiredSpec(context);
    const input = String(node.raw.input || node.raw.prompt || node.name);
    const task = await requiredStore(context).createTask(spec, input, node.name, { ...node.metadata, workflow_node_id: node.node_id });
    if (!context.taskRunner) return { node_id: node.node_id, kind: node.kind, name: node.name, status: "created", task };
    const result = await context.taskRunner.run(task.task_id) as Record<string, unknown>;
    return { node_id: node.node_id, kind: node.kind, name: node.name, status: workflowNodeStatus(result), ...result };
  }

  return { node_id: node.node_id, kind: node.kind, name: node.name, status: "error", error: `workflow node kind is not executable here: ${node.kind}` };
}

function requiredStore(context: ToolExecutionContext) {
  if (!context.store) throw new Error("workflow task store is not available");
  return context.store;
}

function requiredSpec(context: ToolExecutionContext): AgentSpec {
  if (!context.spec) throw new Error("agent spec is not available");
  return context.spec;
}

function workflowNodeStatus(result: Record<string, unknown>): string {
  const nestedResult = result.result;
  if (!nestedResult || typeof nestedResult !== "object" || Array.isArray(nestedResult)) return "finished";
  return String((nestedResult as Record<string, unknown>).status || "finished");
}
