import type {
  ActivityEvent,
  AgentChatPayload,
  ChatMessage,
  OperationEvent
} from "../types/runtimeTypes";
import { createId, seedActivity, welcome } from "./sessionUtils";
import { loadOperationTrace } from "./operationTrace";
import { buildAgentChatPayload, buildAgentScopeFilter } from "./agentRequestPayloads";
import {
  appendUniqueOperationEvents,
  createActivityRecord,
  createChatMessage,
  removeChatMessage,
  updateActivityRecord,
  updateChatMessageContent
} from "./agentSessionRecords";
import { createAgentTaskActions } from "./agentTaskActions";
import { createAgentModelProfileActions } from "./agentModelProfileActions";
import { createAgentHealthActions } from "./agentHealthActions";
import { createAgentConversationActions } from "./agentConversationActions";
import { createAgentSessionState, publicAgentSessionState } from "./agentSessionState";

export function createAgentSession() {
  const state = createAgentSessionState();
  const api = state.api;

  const refreshRuns = async () => {
    const data = await api().runs(scopeFilter());
    state.setRuns(data.runs || []);
  };

  const { refreshTasks, openTask, createTask, runTask, cancelTask } = createAgentTaskActions({
    api,
    payload,
    scopeFilter,
    selectedTaskId: state.selectedTaskId,
    setRunId: state.setRunId,
    setTasks: state.setTasks,
    setTaskSteps: state.setTaskSteps,
    setSelectedTaskId: state.setSelectedTaskId,
    refreshRuns,
    syncOperationTrace,
    eventDeps
  });

  const { refreshModelProfiles, applyModelProfile } = createAgentModelProfileActions({
    api,
    modelProfiles: state.modelProfiles,
    setModelProfiles: state.setModelProfiles,
    setActiveProfile: state.setActiveProfile,
    setProtocol: state.setProtocol,
    setModel: state.setModel,
    setModelBaseUrl: state.setModelBaseUrl
  });

  const { checkHealth } = createAgentHealthActions({ api, setHealth: state.setHealth, record, updateActivity });

  const { send, decideApproval } = createAgentConversationActions({
    api,
    input: state.input,
    busy: state.busy,
    streaming: state.streaming,
    payload,
    setInput: state.setInput,
    setBusy: state.setBusy,
    setRunId: state.setRunId,
    setLatency: state.setLatency,
    setActivity: state.setActivity,
    setOperations: state.setOperations,
    setPendingApprovals: state.setPendingApprovals,
    push,
    removeMessage,
    record,
    updateActivity,
    refreshRuns,
    syncOperationTrace,
    eventDeps,
    streamDeps
  });

  const bootstrap = async () => {
    await Promise.allSettled([checkHealth(), refreshModelProfiles(), refreshRuns(), refreshTasks()]);
  };

  const clear = () => {
    state.setMessages([welcome]);
    state.setActivity(seedActivity());
    state.setOperations([]);
    state.setLatency(null);
    state.setPendingApprovals([]);
  };

  return {
    ...publicAgentSessionState(state),
    send,
    decideApproval,
    clear,
    checkHealth, refreshRuns, refreshTasks, refreshModelProfiles, applyModelProfile, openTask, createTask, runTask, cancelTask, bootstrap
  };

  function payload(message: string): AgentChatPayload {
    return buildAgentChatPayload({
      message,
      protocol: state.protocol(),
      model: state.model(),
      modelBaseUrl: state.modelBaseUrl(),
      apiKey: state.apiKey(),
      systemPrompt: state.systemPrompt(),
      enabledTools: state.toolList(),
      permissionMode: state.permissionMode(),
      tenantId: state.tenantId(),
      userId: state.userId(),
      agentId: state.agentId(),
      workspaceId: state.workspaceId()
    });
  }

  function scopeFilter() {
    return buildAgentScopeFilter({ tenantId: state.tenantId(), userId: state.userId(), agentId: state.agentId() });
  }

  function push(role: ChatMessage["role"], content: string) {
    const id = createId();
    state.setMessages((current) => [...current, createChatMessage(id, role, content)]);
    return id;
  }
  function updateMessage(id: number, content: string, append = false) {
    state.setMessages((current) => updateChatMessageContent(current, id, content, append));
  }
  function removeMessage(id: number) {
    state.setMessages((current) => removeChatMessage(current, id));
  }
  function record(kind: ActivityEvent["kind"], title: string, detail: string, status: ActivityEvent["status"]) {
    const id = createId();
    state.setActivity((current) => [createActivityRecord(id, kind, title, detail, status), ...current]);
    return id;
  }
  function updateActivity(id: number, patch: Partial<ActivityEvent>) {
    state.setActivity((current) => updateActivityRecord(current, id, patch));
  }
  function recordOperation(events: OperationEvent[]) {
    if (!events.length) return;
    state.setOperations((current) => appendUniqueOperationEvents(current, events, 80));
  }
  async function syncOperationTrace(targetRunId = state.runId()) {
    recordOperation(await loadOperationTrace(api(), targetRunId));
  }
  function eventDeps() {
    return { setRunId: state.setRunId, runId: state.runId, setPendingApprovals: state.setPendingApprovals, record, recordOperation };
  }
  function streamDeps() {
    return { ...eventDeps(), updateMessage, updateActivity, removeMessage, push };
  }
}
