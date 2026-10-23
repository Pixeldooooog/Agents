import type { WorkflowNode, WorkflowPlan } from "./workflowModels.js";

export function validateWorkflow(plan: WorkflowPlan): WorkflowNode[] {
  const nodeIds = new Set(plan.nodes.map((node) => node.node_id));
  if (nodeIds.size !== plan.nodes.length) throw new Error("workflow contains duplicate node ids");
  for (const edge of plan.edges) {
    if (!nodeIds.has(edge.source)) throw new Error(`workflow edge source is missing: ${edge.source}`);
    if (!nodeIds.has(edge.target)) throw new Error(`workflow edge target is missing: ${edge.target}`);
  }
  return topologicalNodes(plan);
}

function topologicalNodes(plan: WorkflowPlan): WorkflowNode[] {
  const nodesById = new Map(plan.nodes.map((node) => [node.node_id, node]));
  const incoming = new Map(plan.nodes.map((node) => [node.node_id, 0]));
  const outgoing = new Map(plan.nodes.map((node) => [node.node_id, [] as string[]]));
  for (const edge of plan.edges) {
    incoming.set(edge.target, (incoming.get(edge.target) || 0) + 1);
    outgoing.get(edge.source)?.push(edge.target);
  }

  const ready = [...incoming.entries()].filter(([, count]) => count === 0).map(([nodeId]) => nodeId).sort();
  const orderedNodes: WorkflowNode[] = [];
  while (ready.length) {
    const nodeId = ready.shift()!;
    orderedNodes.push(nodesById.get(nodeId)!);
    for (const target of [...(outgoing.get(nodeId) || [])].sort()) {
      incoming.set(target, (incoming.get(target) || 0) - 1);
      if (incoming.get(target) === 0) ready.push(target);
      ready.sort();
    }
  }
  if (orderedNodes.length !== plan.nodes.length) throw new Error("workflow contains a cycle");
  return orderedNodes;
}
