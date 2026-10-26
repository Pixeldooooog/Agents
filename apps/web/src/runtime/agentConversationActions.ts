import type { Accessor, Setter } from "solid-js";
import type {
  ActivityEvent,
  AgentChatPayload,
  ApprovalDecision,
  ChatMessage,
  OperationEvent,
  ToolApprovalRequest
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
  record: (kind: ActivityEvent["kind"], title: string, detail: string, status: ActivityEvent["status"]) => number;
  updateActivity: (id: number, patch: Partial<ActivityEvent>) => void;
  refreshRuns: () => Promise<void>;
  syncOperationTrace: (runId?: string) => Promise<void>;
  eventDeps: () => RuntimeEventDeps;
  streamDeps: () => StreamEventDeps;
};

export function createAgentConversationActions(options: AgentConversationActionsOptions) {
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
    await options.syncOperationTrace();
    await options.refreshRuns();
  };

  const decideApproval = async (request: ToolApprovalRequest, decision: ApprovalDecision) => {
    options.setBusy(true);
    const approved = decision !== "deny";
    const id = options.record("approval", approvalDecisionTitle(decision), request.toolName, "running");
    try {
      const data = await options.api().approve(request.runId, { approval_id: request.approvalId, approved, decision });
      options.updateActivity(id, { status: "done", detail: "200 OK" });
      options.setPendingApprovals((current) => current.filter((item) => item.approvalId !== request.approvalId));
      consumeRuntimeEvents(data.events || [], options.eventDeps());
      if (data.status !== "awaiting_approval") options.push("assistant", data.content || copy.chat.emptyResponse);
      await options.syncOperationTrace(request.runId);
      await options.refreshRuns();
    } catch (error) {
      options.updateActivity(id, { status: "error", detail: errorText(error) });
      options.push("error", errorText(error));
    } finally {
      options.setBusy(false);
    }
  };

  return { send, decideApproval };

  async function sendChat(text: string) {
    const started = performance.now();
    options.setBusy(true);
    const requestId = options.record("system", copy.activity.modelRequest, "POST /api/v1/agent/chat", "running");
    try {
      const data = await options.api().chat(options.payload(text));
      options.setLatency(Math.round(performance.now() - started));
      options.updateActivity(requestId, { status: "done", detail: "200 OK" });
      options.setRunId(data.run_id || "");
      consumeRuntimeEvents(data.events || [], options.eventDeps());
      if (data.status !== "awaiting_approval") options.push("assistant", data.content || copy.chat.emptyResponse);
    } catch (error) {
      options.updateActivity(requestId, { status: "error", detail: errorText(error) });
      options.push("error", errorText(error));
    } finally {
      options.setBusy(false);
    }
  }

  async function sendStream(text: string) {
    const started = performance.now();
    options.setBusy(true);
    const assistantId = options.push("assistant", "");
    const streamId = options.record("stream", copy.activity.streamOpen, "POST /api/v1/agent/chat/stream", "running");
    try {
      await options.api().chatStream(options.payload(text), (frame) => handleStreamFrame(frame, assistantId, streamId, options.streamDeps()));
      options.setLatency(Math.round(performance.now() - started));
      options.updateActivity(streamId, { status: "done", detail: copy.activity.streamClosed });
    } catch (error) {
      options.removeMessage(assistantId);
      options.updateActivity(streamId, { status: "error", detail: errorText(error) });
      options.push("error", errorText(error));
    } finally {
      options.setBusy(false);
    }
  }
}

function approvalDecisionTitle(decision: ApprovalDecision) {
  return copy.approval.decided[decision] || copy.activity.approvalSent;
}
