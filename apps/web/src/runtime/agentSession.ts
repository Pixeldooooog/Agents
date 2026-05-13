import { createMemo, createSignal } from "solid-js";
import { createApiClient } from "./apiClient";
import type { ActivityEvent, ActivityEventKind, ActivityEventStatus, AgentChatPayload, ApprovalDecision, ChatMessage, ModelProfile, OperationEvent, PermissionMode, RuntimeRun, TaskRecord, TaskStepRecord, ToolApprovalRequest } from "../types";
import { compact, createId, errorText, seedActivity, splitCsv, timeLabel, welcome } from "./sessionUtils";
import { consumeRuntimeEvents, handleStreamFrame } from "./eventHandlers";
import { defaultApiBaseUrl } from "./config";
import { loadOperationTrace } from "./operationTrace";

export function createAgentSession() {
  const [baseUrl, setBaseUrl] = createSignal(defaultApiBaseUrl());
  const [token, setToken] = createSignal("");
  const [protocol, setProtocol] = createSignal("openai-chat");
  const [model, setModel] = createSignal("");
  const [modelBaseUrl, setModelBaseUrl] = createSignal("");
  const [apiKey, setApiKey] = createSignal("");
  const [systemPrompt, setSystemPrompt] = createSignal("You are a precise, helpful agent.");
  const [enabledTools, setEnabledTools] = createSignal("");
  const [permissionMode, setPermissionMode] = createSignal<PermissionMode>("ask");
  const [tenantId, setTenantId] = createSignal("");
  const [userId, setUserId] = createSignal("");
  const [agentId, setAgentId] = createSignal("");
  const [workspaceId, setWorkspaceId] = createSignal("");
  const [streaming, setStreaming] = createSignal(true);
  const [input, setInput] = createSignal("");
  const [messages, setMessages] = createSignal<ChatMessage[]>([welcome]);
  const [activity, setActivity] = createSignal<ActivityEvent[]>(seedActivity());
  const [operations, setOperations] = createSignal<OperationEvent[]>([]);
  const [pendingApprovals, setPendingApprovals] = createSignal<ToolApprovalRequest[]>([]);
  const [runId, setRunId] = createSignal("");
  const [runs, setRuns] = createSignal<RuntimeRun[]>([]);
  const [tasks, setTasks] = createSignal<TaskRecord[]>([]);
  const [taskSteps, setTaskSteps] = createSignal<TaskStepRecord[]>([]);
  const [selectedTaskId, setSelectedTaskId] = createSignal("");
  const [modelProfiles, setModelProfiles] = createSignal<ModelProfile[]>([]);
  const [activeProfile, setActiveProfile] = createSignal("");
  const [busy, setBusy] = createSignal(false);
  const [health, setHealth] = createSignal("unknown");
  const [latency, setLatency] = createSignal<number | null>(null);

  const canSend = createMemo(() => input().trim().length > 0 && !busy());
  const toolList = createMemo(() => splitCsv(enabledTools()));
  const api = createMemo(() => createApiClient({ baseUrl, token }));

  const send = async () => {
    const text = input().trim();
    if (!text || busy()) return;
    push("user", text);
    setInput("");
    setRunId("");
    setPendingApprovals([]);
    setActivity([]);
    setOperations([]);
    if (streaming()) await sendStream(text);
    else await sendChat(text);
    await syncOperationTrace();
    await refreshRuns();
  };

  const sendChat = async (text: string) => {
    const started = performance.now();
    setBusy(true);
    const requestId = record("system", "Model request", "POST /api/v1/agent/chat", "running");
    try {
      const data = await api().chat(payload(text));
      setLatency(Math.round(performance.now() - started));
      updateActivity(requestId, { status: "done", detail: "200 OK" });
      setRunId(data.run_id || "");
      consumeRuntimeEvents(data.events || [], eventDeps());
      if (data.status !== "awaiting_approval") push("assistant", data.content || "(empty response)");
    } catch (error) {
      updateActivity(requestId, { status: "error", detail: errorText(error) });
      push("error", errorText(error));
    } finally {
      setBusy(false);
    }
  };

  const sendStream = async (text: string) => {
    const started = performance.now();
    setBusy(true);
    const assistantId = push("assistant", "");
    const streamId = record("stream", "Streaming response", "Opening event stream", "running");
    try {
      await api().chatStream(payload(text), (frame) => handleStreamFrame(frame, assistantId, streamId, streamDeps()));
      setLatency(Math.round(performance.now() - started));
      updateActivity(streamId, { status: "done", detail: "Response stream closed" });
    } catch (error) {
      removeMessage(assistantId);
      updateActivity(streamId, { status: "error", detail: errorText(error) });
      push("error", errorText(error));
    } finally {
      setBusy(false);
    }
  };

  const decideApproval = async (request: ToolApprovalRequest, decision: ApprovalDecision) => {
    setBusy(true);
    const approved = decision !== "deny";
    const id = record("approval", approvalDecisionTitle(decision), request.toolName, "running");
    try {
      const data = await api().approve(request.runId, { tool_call_ids: [request.approvalId], approved, decision });
      updateActivity(id, { status: "done", detail: "200 OK" });
      setPendingApprovals((current) => current.filter((item) => item.approvalId !== request.approvalId));
      consumeRuntimeEvents(data.events || [], eventDeps());
      if (data.status !== "awaiting_approval") push("assistant", data.content || "(empty response)");
      await syncOperationTrace(request.runId);
      await refreshRuns();
    } catch (error) {
      updateActivity(id, { status: "error", detail: errorText(error) });
      push("error", errorText(error));
    } finally {
      setBusy(false);
    }
  };

  const refreshRuns = async () => {
    const data = await api().runs(scopeFilter());
    setRuns(data.runs || []);
  };

  const refreshTasks = async () => {
    const data = await api().tasks(scopeFilter());
    setTasks(data.tasks || []);
  };

  const openTask = async (taskId: string) => {
    const data = await api().task(taskId);
    setSelectedTaskId(taskId);
    setTaskSteps(data.steps || []);
  };

  const createTask = async (message: string, title = "") => {
    if (!message.trim()) return;
    await api().createTask({ ...payload(message), title: title || undefined });
    await refreshTasks();
  };

  const runTask = async (taskId: string) => {
    const data = await api().runTask(taskId);
    setRunId(data.run?.run_id || "");
    consumeRuntimeEvents(data.result?.events || data.run?.events || [], eventDeps());
    await syncOperationTrace(data.run?.run_id || "");
    await refreshTasks();
    await refreshRuns();
    await openTask(taskId);
  };

  const cancelTask = async (taskId: string) => {
    await api().cancelTask(taskId);
    await refreshTasks();
    if (selectedTaskId() === taskId) await openTask(taskId);
  };

  const refreshModelProfiles = async () => {
    const data = await api().modelProfiles();
    setModelProfiles(data.profiles || []);
    setActiveProfile(data.active_profile || "");
  };

  const applyModelProfile = (name: string) => {
    const target = modelProfiles().find((item) => item.name === name);
    if (!target) return;
    setActiveProfile(target.name);
    setProtocol(target.protocol);
    setModel(target.model);
    setModelBaseUrl(target.base_url);
  };

  const checkHealth = async () => {
    const id = record("system", "Health probe", "GET /health", "running");
    try {
      await api().health();
      setHealth("online");
      updateActivity(id, { status: "done", detail: "200 OK" });
    } catch (error) {
      setHealth("offline");
      updateActivity(id, { status: "error", detail: errorText(error) });
    }
  };

  const bootstrap = async () => {
    await Promise.allSettled([checkHealth(), refreshModelProfiles(), refreshRuns(), refreshTasks()]);
  };

  const clear = () => {
    setMessages([welcome]);
    setActivity(seedActivity());
    setOperations([]);
    setLatency(null);
    setPendingApprovals([]);
  };

  return {
    baseUrl, setBaseUrl, token, setToken, protocol, setProtocol, model, setModel, modelBaseUrl, setModelBaseUrl, apiKey, setApiKey,
    systemPrompt, setSystemPrompt, enabledTools, setEnabledTools, permissionMode, setPermissionMode, tenantId, setTenantId, userId, setUserId,
    agentId, setAgentId, workspaceId, setWorkspaceId, streaming, setStreaming, input, setInput, messages, activity, pendingApprovals, runId, setRunId,
    runs, tasks, taskSteps, selectedTaskId, modelProfiles, activeProfile, busy, health, latency, operations, canSend, toolList, send, decideApproval, clear,
    checkHealth, refreshRuns, refreshTasks, refreshModelProfiles, applyModelProfile, openTask, createTask, runTask, cancelTask, bootstrap
  };

  function payload(message: string): AgentChatPayload {
    return compact({
      message,
      protocol: protocol(),
      model: model(),
      base_url: modelBaseUrl(),
      api_key: apiKey(),
      system_prompt: systemPrompt(),
      enabled_tools: toolList(),
      permission_profile: permissionMode(),
      tenant_id: tenantId(),
      user_id: userId(),
      agent_id: agentId(),
      workspace_id: workspaceId()
    }) as AgentChatPayload;
  }

  function scopeFilter() {
    return compact({ tenant_id: tenantId(), user_id: userId(), agent_id: agentId() }) as Record<string, string>;
  }

  function push(role: ChatMessage["role"], content: string) {
    const id = createId();
    setMessages((current) => [...current, { id, role, content }]);
    return id;
  }
  function updateMessage(id: number, content: string, append = false) {
    setMessages((current) => current.map((item) => item.id === id ? { ...item, content: append ? `${item.content}${content}` : content } : item));
  }
  function removeMessage(id: number) { setMessages((current) => current.filter((item) => item.id !== id)); }
  function record(kind: ActivityEventKind, title: string, detail: string, status: ActivityEventStatus) {
    const id = createId();
    setActivity((current) => [{ id, kind, title, detail, status, time: timeLabel() }, ...current]);
    return id;
  }
  function updateActivity(id: number, patch: Partial<ActivityEvent>) {
    setActivity((current) => current.map((item) => item.id === id ? { ...item, ...patch } : item));
  }
  function recordOperation(events: OperationEvent[]) {
    if (!events.length) return;
    setOperations((current) => {
      const seen = new Set(current.map((event) => event.id));
      return [...current, ...events.filter((event) => !seen.has(event.id))].slice(-80);
    });
  }
  async function syncOperationTrace(targetRunId = runId()) {
    recordOperation(await loadOperationTrace(api(), targetRunId));
  }
  function eventDeps() {
    return { setRunId, runId, setPendingApprovals, record, recordOperation };
  }
  function streamDeps() {
    return { ...eventDeps(), updateMessage, updateActivity, removeMessage, push };
  }
}
function approvalDecisionTitle(decision: ApprovalDecision) {
  return decision === "allow_for_run" ? "Tool allowed for run" : decision === "allow_once" ? "Tool allowed once" : "Tool denied";
}
