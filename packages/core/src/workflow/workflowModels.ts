import { validateWorkflow } from "./workflowGraph.js";
import type { JsonObject } from "../types/jsonTypes.js";

export { validateWorkflow } from "./workflowGraph.js";

export type WorkflowNode = {
  node_id: string;
  kind: string;
  name: string;
  metadata: Record<string, string>;
  raw: Record<string, unknown>;
};

export type WorkflowEdge = {
  source: string;
  target: string;
  condition: string;
};

export type WorkflowPlan = {
  workflow_id: string;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  metadata: Record<string, string>;
};

const workflowNodeKinds = ["task", "agent", "tool", "human_approval"];

export function workflowPlan(args: JsonObject, fallbackId: string): WorkflowPlan {
  const nodes = Array.isArray(args.nodes) ? args.nodes.map((node, index) => workflowNode(node, index + 1)) : [];
  const edges = Array.isArray(args.edges) ? args.edges.map(workflowEdge) : [];
  return { workflow_id: String(args.workflow_id || fallbackId || "workflow"), nodes, edges, metadata: stringRecord(args.metadata) };
}

export function parseWorkflowJson(content: string, name: string): Record<string, unknown> {
  const payload = JSON.parse(content || "{}");
  if (!payload || typeof payload !== "object") throw new Error(`workflow must be a JSON object: ${name}`);
  const plan = workflowPlan(payload as JsonObject, name);
  validateWorkflow(plan);
  return workflowPayload(plan);
}

export function workflowPayload(plan: WorkflowPlan): Record<string, unknown> {
  return {
    workflow_id: plan.workflow_id,
    nodes: plan.nodes.map(nodePayload),
    edges: plan.edges,
    metadata: plan.metadata
  };
}

export function nodePayload(node: WorkflowNode): Record<string, unknown> {
  const payload: Record<string, unknown> = { node_id: node.node_id, kind: node.kind, name: node.name, metadata: node.metadata };
  for (const key of ["input", "prompt", "agent_id", "system_prompt", "enabled_tools"]) if (key in node.raw) payload[key] = node.raw[key];
  return payload;
}

export function workflowSummary(name: string, filePath: string, payload: Record<string, unknown>): Record<string, unknown> {
  const nodes = Array.isArray(payload.nodes) ? payload.nodes as Record<string, unknown>[] : [];
  return {
    name,
    path: filePath,
    workflow_id: String(payload.workflow_id || name),
    node_count: nodes.length,
    metadata: stringRecord(payload.metadata),
    preview: nodes.map((node) => String(node.name || node.node_id || "")).filter(Boolean).join(", ").slice(0, 160)
  };
}

export function workflowStatus(results: Record<string, unknown>[]): string {
  const statuses = new Set(results.map((result) => String(result.status || "")));
  if (statuses.has("error")) return "error";
  if (statuses.has("awaiting_approval")) return "awaiting_approval";
  return "finished";
}

export function workflowHaystack(workflow: Record<string, unknown>): string {
  return [
    workflow.name,
    workflow.workflow_id,
    workflow.preview,
    workflow.error,
    Object.entries(stringRecord(workflow.metadata)).map(([key, value]) => `${key} ${value}`).join(" ")
  ].join(" ").toLowerCase();
}

export function stringRecord(rawRecord: unknown): Record<string, string> {
  if (!rawRecord || typeof rawRecord !== "object") return {};
  return Object.fromEntries(Object.entries(rawRecord).map(([key, rawValue]) => [String(key), String(rawValue)]));
}

export function requiredText(rawText: unknown, fieldName: string): string {
  const text = String(rawText || "").trim();
  if (!text) throw new Error(`${fieldName} is required`);
  return text;
}

export function boundedLimit(rawLimit: unknown, fallback: number): number {
  const limit = Number(rawLimit || fallback);
  if (!Number.isFinite(limit)) return fallback;
  return Math.max(1, Math.min(100, limit));
}

function workflowNode(rawNode: unknown, index: number): WorkflowNode {
  if (!rawNode || typeof rawNode !== "object") throw new Error("workflow nodes must be objects");
  const record = rawNode as Record<string, unknown>;
  const kind = String(record.kind || "");
  if (!workflowNodeKinds.includes(kind)) throw new Error(`unknown workflow node kind: ${kind}`);
  const nodeId = safeNodeId(String(record.node_id || record.id || `node_${index}`));
  return { node_id: nodeId, kind, name: requiredText(record.name, "name"), metadata: stringRecord(record.metadata), raw: record };
}

function workflowEdge(rawEdge: unknown): WorkflowEdge {
  if (!rawEdge || typeof rawEdge !== "object") throw new Error("workflow edges must be objects");
  const record = rawEdge as Record<string, unknown>;
  return { source: safeNodeId(String(record.source || "")), target: safeNodeId(String(record.target || "")), condition: String(record.condition || "") };
}

function safeNodeId(rawNodeId: string): string {
  return [...String(rawNodeId || "").trim()].map((char) => /[a-zA-Z0-9_.-]/.test(char) ? char : "_").join("").replace(/^[._-]+|[._-]+$/g, "") || "node";
}
