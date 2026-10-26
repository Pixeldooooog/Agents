import { approvalFromEvent, mergeApproval } from "./sessionUtils";
import { projectRuntimeEvent } from "./operationProjector";
import type { ActivityEventKind, ActivityEventStatus, OperationEvent, SseEventFrame, ToolApprovalRequest } from "../types/runtimeTypes";
import { copy } from "../copy";

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
      deps.record("approval", copy.activity.approvalRequired, request.toolName, "waiting");
    } else if (event.type === "tool_start") deps.record("tool", copy.activity.toolStarted, event.name || "tool", "running");
    else if (event.type === "tool_result") deps.record("tool", copy.activity.toolFinished, event.name || "tool", event.payload?.is_error ? "error" : "done");
    else if (event.type === "code_start") deps.record("code", copy.activity.codeStarted, event.payload?.language || "runtime code", "running");
    else if (event.type === "web_search") deps.record("search", copy.activity.webSearch, event.payload?.query || "search", "running");
    else if (event.type === "browser_action") deps.record("browser", copy.activity.browserAction, event.payload?.action || "browser step", "running");
    else if (event.type === "error") deps.record("error", copy.activity.streamError, event.payload?.message || copy.activity.streamError, "error");
    else if (event.type !== "done") deps.record("stream", event.type || "event", JSON.stringify(event.payload || event), "done");
  }
}

export function handleStreamFrame(frame: SseEventFrame, assistantId: number, streamId: number, deps: StreamDeps) {
  if (frame.event === "text_delta") {
    const delta = frame.payload?.payload?.delta || frame.payload?.delta || "";
    deps.updateMessage(assistantId, delta, true);
    deps.updateActivity(streamId, { detail: copy.activity.streamDelta(delta.length) });
    return;
  }
  if (frame.event === "done") {
    const result = frame.payload?.payload || frame.payload;
    if (result?.status === "awaiting_approval" && !result?.content) deps.removeMessage(assistantId);
    else deps.updateMessage(assistantId, result?.content || "");
  }
  if (frame.event === "error") {
    deps.removeMessage(assistantId);
    deps.push("error", frame.payload?.payload?.message || frame.payload?.message || copy.activity.streamError);
  }
  consumeRuntimeEvents([{ type: frame.event, name: frame.payload?.name, payload: frame.payload?.payload || frame.payload }], deps);
}
