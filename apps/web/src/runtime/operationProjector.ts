import type { OperationEvent, OperationPhase, OperationSceneKind } from "../types/runtimeTypes";
import { operationFromFrame } from "./operationFrames";
import { fileHistoryOperation } from "./operationSpecialEvents";
import { createId } from "./sessionUtils";
import {
  detailForTool,
  sceneForTool,
  targetForTool,
  titleForTool
} from "./operationToolPresentation";
import {
  artifactsFromResult,
  diffFromResult,
  filesFromResult,
  previewResult,
  scrubArgs,
  sourcesFromResult,
  statsFromResult
} from "./operationResultPreviews";

type RuntimeEvent = {
  type?: string;
  name?: string;
  payload?: Record<string, any>;
};

export function projectRuntimeEvent(event: RuntimeEvent, runId = ""): OperationEvent[] {
  if (event.type === "operation_frame") return [operationFromFrame(event.payload || {}, runId)];
  if (event.type === "tool_start") return [operationFromToolEvent(event, "opening", runId)];
  if (event.type === "tool_result") return [operationFromToolEvent(event, event.payload?.is_error ? "error" : "done", runId)];
  if (event.type === "file_history_write") return [fileHistoryOperation(event, runId)];
  if (event.type === "web_search") return [genericOperation(event, "web", "web.search", "opening", runId)];
  if (event.type === "browser_action") return [genericOperation(event, "browser", "browser.action", "opening", runId)];
  if (event.type === "code_start") return [genericOperation(event, "terminal", "code.run", "opening", runId)];
  if (event.type === "done") {
    return [{
      id: `summary:${createId()}`,
      runId,
      toolCallId: "",
      toolName: "assistant.done",
      scene: "summary",
      phase: event.payload?.error ? "error" : "done",
      title: event.payload?.error ? "Run ended with an error" : "Run complete",
      detail: event.payload?.error || "Windows closed. Result returned to chat.",
      resultPreview: event.payload
    }];
  }
  return [];
}

function operationFromToolEvent(event: RuntimeEvent, phase: OperationPhase, fallbackRunId: string): OperationEvent {
  const payload = event.payload || {};
  const call = payload.tool_call || payload;
  const toolName = call.name || payload.name || event.name || "tool";
  const args = call.arguments || payload.arguments || {};
  const result = payload.raw || payload.result || payload.content || payload;
  return {
    id: `${call.id || payload.tool_call_id || toolName}:${phase}:${createId()}`,
    runId: payload.run_id || fallbackRunId,
    toolCallId: call.id || payload.tool_call_id || "",
    toolName,
    scene: sceneForTool(toolName),
    phase,
    title: titleForTool(toolName, phase),
    target: targetForTool(toolName, args, result),
    detail: detailForTool(toolName, args, result),
    argsPreview: scrubArgs(args),
    resultPreview: previewResult(result),
    diffPreview: diffFromResult(result),
    artifacts: artifactsFromResult(result),
    sources: sourcesFromResult(result),
    files: filesFromResult(toolName, args, result),
    stats: statsFromResult(result),
    startedAt: phase === "opening" ? Date.now() : undefined,
    endedAt: phase === "done" || phase === "error" ? Date.now() : undefined
  };
}

function genericOperation(event: RuntimeEvent, scene: OperationSceneKind, toolName: string, phase: OperationPhase, runId: string): OperationEvent {
  const payload = event.payload || {};
  return {
    id: `${toolName}:${phase}:${createId()}`,
    runId: payload.run_id || runId,
    toolCallId: "",
    toolName: event.name || toolName,
    scene,
    phase,
    title: titleForTool(event.name || toolName, phase),
    target: targetForTool(event.name || toolName, payload, payload),
    detail: detailForTool(event.name || toolName, payload, payload),
    argsPreview: scrubArgs(payload),
    sources: sourcesFromResult(payload),
    startedAt: Date.now(),
  };
}
