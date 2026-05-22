import type { OperationEvent } from "../types";
import { createId } from "./sessionUtils";

type RuntimeEvent = {
  type?: string;
  name?: string;
  payload?: Record<string, any>;
};

export function fileHistoryOperation(event: RuntimeEvent, fallbackRunId: string): OperationEvent {
  const payload = event.payload || {};
  const path = String(payload.path || "");
  const operation = String(payload.operation || "write");
  const toolName = String(payload.canonical_tool || event.name || payload.tool_name || "file_history");
  return {
    id: `file-history:${path || toolName}:${createId()}`,
    runId: payload.run_id || fallbackRunId,
    toolCallId: "",
    toolName,
    scene: "edit",
    phase: "done",
    title: "File history checkpoint pending",
    target: path || toolName,
    detail: `${operation} recorded for file-history checkpointing`,
    files: path ? [{ path, status: operation }] : undefined,
    stats: {
      checkpoint_pending: payload.checkpoint_pending ?? true,
      operation,
      source: payload.source || "tool_result",
      tool_name: payload.tool_name || toolName
    },
    source: "file_history",
    endedAt: Date.now(),
  };
}
