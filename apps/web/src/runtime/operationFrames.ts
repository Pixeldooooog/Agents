import type { OperationEvent, OperationPhase, OperationSceneKind } from "../types";
import { createId } from "./sessionUtils";
import { isEditTool } from "./operationToolMapping";

const scenes: OperationSceneKind[] = ["workspace", "edit", "web", "browser", "terminal", "git", "document", "summary"];
const phases: OperationPhase[] = ["opening", "running", "closing", "done", "error"];

export function operationFromFrame(frame: Record<string, any>, fallbackRunId: string): OperationEvent {
  const toolName = String(frame.toolName || frame.tool_name || frame.name || "workspace");
  const phase = normalizePhase(frame.phase);
  return {
    id: String(frame.id || `operation:${toolName}:${phase}:${createId()}`),
    runId: String(frame.runId || frame.run_id || fallbackRunId),
    toolCallId: String(frame.toolCallId || frame.tool_call_id || ""),
    toolName,
    scene: normalizeScene(frame.scene, toolName),
    phase,
    title: String(frame.title || titleForTool(toolName, phase)),
    target: text(frame.target),
    detail: text(frame.detail),
    argsPreview: frame.argsPreview || frame.args_preview || undefined,
    resultPreview: frame.resultPreview ?? frame.result_preview,
    diffPreview: frame.diffPreview ?? frame.diff_preview,
    artifacts: Array.isArray(frame.artifacts) ? frame.artifacts : undefined,
    sources: Array.isArray(frame.sources) ? frame.sources : undefined,
    files: Array.isArray(frame.files) ? frame.files : undefined,
    stats: frame.stats && typeof frame.stats === "object" ? frame.stats : undefined,
    sequence: typeof frame.sequence === "number" ? frame.sequence : undefined,
    source: text(frame.source) || "sandbox_trace",
    step: stepFromFrame(frame.step),
    startedAt: typeof frame.startedAt === "number" ? frame.startedAt : frame.started_at,
    endedAt: typeof frame.endedAt === "number" ? frame.endedAt : frame.ended_at,
  };
}

function stepFromFrame(step: unknown) {
  if (!step || typeof step !== "object") return undefined;
  const payload = step as Record<string, unknown>;
  const label = text(payload.label);
  return label ? { label, detail: text(payload.detail) } : undefined;
}

function normalizeScene(value: unknown, toolName: string): OperationSceneKind {
  return scenes.includes(value as OperationSceneKind) ? value as OperationSceneKind : sceneForTool(toolName);
}

function normalizePhase(value: unknown): OperationPhase {
  return phases.includes(value as OperationPhase) ? value as OperationPhase : "running";
}

function sceneForTool(toolName: string): OperationSceneKind {
  if (isEditTool(toolName)) return "edit";
  if (toolName.startsWith("web.")) return "web";
  if (toolName.startsWith("browser.")) return "browser";
  if (toolName.startsWith("shell.") || toolName.startsWith("test.")) return "terminal";
  if (toolName.startsWith("git.")) return "git";
  if (toolName.startsWith("skill.") || toolName.startsWith("prompt.") || toolName.startsWith("mcp.") || toolName.startsWith("context.")) return "document";
  if (toolName.startsWith("todo.") || toolName.startsWith("plan.") || toolName.startsWith("task.") || toolName.startsWith("schedule.")) return "document";
  if (toolName.startsWith("workflow.") || toolName.startsWith("agent.") || toolName.startsWith("team.")) return "document";
  return "workspace";
}

function titleForTool(toolName: string, phase: OperationPhase) {
  const verb = phase === "done" ? "Completed" : phase === "error" ? "Failed" : phase === "closing" ? "Closing" : "Operating";
  if (toolName.startsWith("web.")) return `${verb} web workspace`;
  if (toolName.startsWith("browser.")) return `${verb} browser`;
  if (toolName.startsWith("shell.") || toolName.startsWith("test.")) return `${verb} terminal`;
  if (toolName.startsWith("git.")) return `${verb} git terminal`;
  if (isEditTool(toolName)) return `${verb} editor`;
  if (toolName.startsWith("skill.") || toolName.startsWith("mcp.") || toolName.startsWith("prompt.") || toolName.startsWith("context.")) return `${verb} document reader`;
  return `${verb} workspace`;
}

function text(value: unknown) {
  return typeof value === "string" && value ? value : undefined;
}
