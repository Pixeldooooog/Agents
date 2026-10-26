import { createMemo, createSignal } from "solid-js";
import { createApiClient } from "./apiClient";
import type {
  ActivityEvent,
  ChatMessage,
  ModelProfile,
  OperationEvent,
  PermissionMode,
  RuntimeRun,
  TaskRecord,
  TaskStepRecord,
  ToolApprovalRequest
} from "../types/runtimeTypes";
import { defaultApiBaseUrl } from "./config";
import { seedActivity, splitCsv, welcome } from "./sessionUtils";

export function createAgentSessionState() {
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
  const [showDetails, setShowDetails] = createSignal(false);
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

  return {
    baseUrl, setBaseUrl,
    token, setToken,
    protocol, setProtocol,
    model, setModel,
    modelBaseUrl, setModelBaseUrl,
    apiKey, setApiKey,
    systemPrompt, setSystemPrompt,
    enabledTools, setEnabledTools,
    permissionMode, setPermissionMode,
    tenantId, setTenantId,
    userId, setUserId,
    agentId, setAgentId,
    workspaceId, setWorkspaceId,
    streaming, setStreaming,
    showDetails, setShowDetails,
    input, setInput,
    messages, setMessages,
    activity, setActivity,
    pendingApprovals, setPendingApprovals,
    runId, setRunId,
    runs, setRuns,
    tasks, setTasks,
    taskSteps, setTaskSteps,
    selectedTaskId, setSelectedTaskId,
    modelProfiles, setModelProfiles,
    activeProfile, setActiveProfile,
    busy, setBusy,
    health, setHealth,
    latency, setLatency,
    operations, setOperations,
    canSend,
    toolList,
    api
  };
}

export type AgentSessionState = ReturnType<typeof createAgentSessionState>;

export function publicAgentSessionState(state: AgentSessionState) {
  return {
    baseUrl: state.baseUrl,
    setBaseUrl: state.setBaseUrl,
    token: state.token,
    setToken: state.setToken,
    protocol: state.protocol,
    setProtocol: state.setProtocol,
    model: state.model,
    setModel: state.setModel,
    modelBaseUrl: state.modelBaseUrl,
    setModelBaseUrl: state.setModelBaseUrl,
    apiKey: state.apiKey,
    setApiKey: state.setApiKey,
    systemPrompt: state.systemPrompt,
    setSystemPrompt: state.setSystemPrompt,
    enabledTools: state.enabledTools,
    setEnabledTools: state.setEnabledTools,
    permissionMode: state.permissionMode,
    setPermissionMode: state.setPermissionMode,
    tenantId: state.tenantId,
    setTenantId: state.setTenantId,
    userId: state.userId,
    setUserId: state.setUserId,
    agentId: state.agentId,
    setAgentId: state.setAgentId,
    workspaceId: state.workspaceId,
    setWorkspaceId: state.setWorkspaceId,
    streaming: state.streaming,
    setStreaming: state.setStreaming,
    showDetails: state.showDetails,
    setShowDetails: state.setShowDetails,
    input: state.input,
    setInput: state.setInput,
    messages: state.messages,
    activity: state.activity,
    pendingApprovals: state.pendingApprovals,
    runId: state.runId,
    setRunId: state.setRunId,
    runs: state.runs,
    tasks: state.tasks,
    taskSteps: state.taskSteps,
    selectedTaskId: state.selectedTaskId,
    modelProfiles: state.modelProfiles,
    activeProfile: state.activeProfile,
    busy: state.busy,
    health: state.health,
    latency: state.latency,
    operations: state.operations,
    canSend: state.canSend,
    toolList: state.toolList
  };
}
