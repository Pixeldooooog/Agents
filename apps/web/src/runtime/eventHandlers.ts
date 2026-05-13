import { approvalFromEvent, mergeApproval } from "./sessionUtils";
import { projectRuntimeEvent } from "./operationProjector";
import type { ActivityEventKind, ActivityEventStatus, OperationEvent, SseEventFrame, ToolApprovalRequest } from "../types";

type EventDeps = {
  setRunId: (value: string) => void;
  runId: () => string;
  setPendingApprovals: (value: (current: ToolApprovalRequest[]) => ToolApprovalRequest[]) => void;
  record: (kind: ActivityEventKind, title: string, detail: string, status: ActivityEventStatus) => number;
  recordOperation?: (events: OperationEvent[]) => void;
};

type StreamDeps = EventDeps & {
  updateMessage: (id: number, content: string, append?: boolean) => void;
  updateActivity: (id: number, patch: { detail?: string }) => void;
  removeMessage: (id: number) => void;
  push: (role: "error", content: string) => number;
};

export function consumeRuntimeEvents(events: any[], deps: EventDeps) {
  for (const event of events) {
    deps.recordOperation?.(projectRuntimeEvent(event, deps.runId()));
    if (event.type === "run_created") deps.setRunId(event.payload?.run_id || "");
    else if (event.type === "tool_approval_required") {
      const request = approvalFromEvent(event, deps.runId());
      deps.setPendingApprovals((current) => mergeApproval(current, request));
      deps.record("approval", "Approval required", request.toolName, "waiting");
    } else if (event.type === "tool_start") deps.record("tool", "Tool call", event.name || "tool", "running");
    else if (event.type === "tool_result") deps.record("tool", "Tool result", event.name || "tool", "done");
    else if (event.type === "code_start") deps.record("code", "Code execution", event.payload?.language || "runtime code", "running");
    else if (event.type === "web_search") deps.record("search", "Web search", event.payload?.query || "search", "running");
    else if (event.type === "browser_action") deps.record("browser", "Browser action", event.payload?.action || "browser step", "running");
    else if (event.type === "error") deps.record("error", "Stream error", event.payload?.message || "stream error", "error");
    else if (event.type !== "done") deps.record("stream", event.type || "event", JSON.stringify(event.payload || event), "done");
  }
}

export function handleStreamFrame(frame: SseEventFrame, assistantId: number, streamId: number, deps: StreamDeps) {
  if (frame.event === "text_delta") {
    const delta = frame.payload?.payload?.delta || frame.payload?.delta || "";
    deps.updateMessage(assistantId, delta, true);
    deps.updateActivity(streamId, { detail: `Streaming text delta: ${delta.length} chars` });
    return;
  }
  if (frame.event === "done") deps.updateMessage(assistantId, frame.payload?.payload?.content || frame.payload?.content || "");
  if (frame.event === "error") {
    deps.removeMessage(assistantId);
    deps.push("error", frame.payload?.payload?.message || frame.payload?.message || "stream error");
  }
  consumeRuntimeEvents([{ type: frame.event, name: frame.payload?.name, payload: frame.payload?.payload || frame.payload }], deps);
}
