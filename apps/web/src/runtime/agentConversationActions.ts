import type { Accessor, Setter } from "solid-js";
import type {
  ActivityEvent,
  AgentChatPayload,
  ApprovalDecision,
  ChatMessage,
  OperationEvent,
  ToolApprovalRequest,
} from "../types/runtimeTypes";
import type { createApiClient } from "./apiClient";
import { consumeRuntimeEvents, handleStreamFrame } from "./eventHandlers";
import { errorText } from "./sessionUtils";
import { copy } from "../copy";

type ApiClient = ReturnType<typeof createApiClient>;
type RuntimeEventDeps = Parameters<typeof consumeRuntimeEvents>[1];
type StreamEventDeps = Parameters<typeof handleStreamFrame>[3];

type AgentConversationActionsOptions = {
  api: () => ApiClient;
  input: Accessor<string>;
  busy: Accessor<boolean>;
  streaming: Accessor<boolean>;
  payload: (message: string) => AgentChatPayload;
  setInput: Setter<string>;
  setBusy: Setter<boolean>;
  setRunId: Setter<string>;
  setLatency: Setter<number | null>;
  setActivity: Setter<ActivityEvent[]>;
  setOperations: Setter<OperationEvent[]>;
  setPendingApprovals: Setter<ToolApprovalRequest[]>;
  push: (role: ChatMessage["role"], content: string) => number;
  removeMessage: (id: number) => void;
  record: (
    kind: ActivityEvent["kind"],
    title: string,
    detail: string,
    status: ActivityEvent["status"],
  ) => number;
  updateActivity: (id: number, patch: Partial<ActivityEvent>) => void;
  refreshRuns: () => Promise<void>;
  syncOperationTrace: (runId?: string) => Promise<void>;
  eventDeps: () => RuntimeEventDeps;
  streamDeps: () => StreamEventDeps;
};

export function createAgentConversationActions(
  options: AgentConversationActionsOptions,
) {
  let previousRunId: string | undefined;
  const resetConversation = () => {
    previousRunId = undefined;
  };
  const payload = (text: string) => ({
    ...options.payload(text),
    previous_run_id: previousRunId,
  });
  let activeRequest: AbortController | undefined;
  const cancel = () => activeRequest?.abort();
  const send = async () => {
    const text = options.input().trim();
    if (!text || options.busy()) return;
    options.push("user", text);
    options.setInput("");
    options.setRunId("");
    options.setPendingApprovals([]);
    options.setActivity([]);
    options.setOperations([]);
    if (options.streaming()) await sendStream(text);
    else await sendChat(text);
    try {
      await options.syncOperationTrace();
      await options.refreshRuns();
    } catch (error) {
      options.record("error", "运行记录刷新失败", errorText(error), "error");
    }
  };

  const decideApproval = async (
    request: ToolApprovalRequest,
    decision: ApprovalDecision,
  ) => {
    activeRequest = new AbortController();
    options.setBusy(true);
    const approved = decision !== "deny";
    const id = options.record(
      "approval",
      approvalDecisionTitle(decision),
      request.toolName,
      "running",
    );
    try {
      const data = await options
        .api()
        .approve(
          request.runId,
          { approval_id: request.approvalId, approved, decision },
          activeRequest.signal,
        );
      options.updateActivity(id, { status: "done", detail: "200 OK" });
      options.setPendingApprovals((current) =>
        current.filter((item) => item.approvalId !== request.approvalId),
      );
      if (data.status === "completed") previousRunId = data.run_id;
      consumeRuntimeEvents(data.events || [], options.eventDeps());
      if (data.status !== "waiting_approval")
        options.push("assistant", data.content || copy.chat.emptyResponse);
      await options.syncOperationTrace(request.runId);
      await options.refreshRuns();
    } catch (error) {
      options.updateActivity(id, { status: "error", detail: errorText(error) });
      if (activeRequest?.signal.aborted)
        options.push("event", "已停止这次请求。你可以调整想法后继续。");
      else options.push("error", errorText(error));
    } finally {
      activeRequest = undefined;
      options.setBusy(false);
    }
  };

  return { send, decideApproval, cancel, resetConversation };

  async function sendChat(text: string) {
    const started = performance.now();
    activeRequest = new AbortController();
    options.setBusy(true);
    const requestId = options.record(
      "system",
      copy.activity.modelRequest,
      "POST /api/v1/agent/chat",
      "running",
    );
    try {
      const data = await options
        .api()
        .chat(payload(text), activeRequest.signal);
      options.setLatency(Math.round(performance.now() - started));
      options.updateActivity(requestId, { status: "done", detail: "200 OK" });
      options.setRunId(data.run_id || "");
      if (data.status === "completed") previousRunId = data.run_id;
      consumeRuntimeEvents(data.events || [], options.eventDeps());
      if (data.status !== "waiting_approval")
        options.push("assistant", data.content || copy.chat.emptyResponse);
    } catch (error) {
      options.updateActivity(requestId, {
        status: "error",
        detail: errorText(error),
      });
      if (activeRequest?.signal.aborted)
        options.push("event", "已停止这次请求。你可以调整想法后继续。");
      else options.push("error", errorText(error));
    } finally {
      activeRequest = undefined;
      options.setBusy(false);
    }
  }

  async function sendStream(text: string) {
    let currentRunId: string | undefined;
    let completed = false;
    const started = performance.now();
    activeRequest = new AbortController();
    options.setBusy(true);
    const assistantId = options.push("assistant", "");
    const streamId = options.record(
      "stream",
      copy.activity.streamOpen,
      "POST /api/v1/agent/chat/stream",
      "running",
    );
    try {
      await options.api().chatStream(
        payload(text),
        (frame) => {
          if (
            frame.event === "run_created" &&
            typeof frame.payload.payload?.run_id === "string"
          )
            currentRunId = frame.payload.payload.run_id;
          if (frame.event === "done")
            completed = frame.payload.payload?.status === "completed";
          handleStreamFrame(frame, assistantId, streamId, options.streamDeps());
        },
        activeRequest.signal,
      );
      if (completed) previousRunId = currentRunId;
      options.setLatency(Math.round(performance.now() - started));
      options.updateActivity(streamId, {
        status: "done",
        detail: copy.activity.streamClosed,
      });
    } catch (error) {
      options.removeMessage(assistantId);
      options.updateActivity(streamId, {
        status: "error",
        detail: errorText(error),
      });
      if (activeRequest?.signal.aborted)
        options.push("event", "已停止这次请求。你可以调整想法后继续。");
      else options.push("error", errorText(error));
    } finally {
      activeRequest = undefined;
      options.setBusy(false);
    }
  }
}

function approvalDecisionTitle(decision: ApprovalDecision) {
  return copy.approval.decided[decision] || copy.activity.approvalSent;
}
