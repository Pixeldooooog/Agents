import { loadSettings, type Settings } from "../config/settings.js";
import { AgentRunService, type AgentRunServiceOptions } from "../runtime/agentRunService.js";
import { JsonStateStore, statePath } from "../store/jsonStateStore.js";
import type { StoreScopeFilter } from "../store/storeFilters.js";
import { TaskService } from "../tasks/taskService.js";
import { resolveTaskInScope } from "../tasks/taskResolution.js";
import type { AgentSpec } from "../types/agentTypes.js";
import type { McpServerRecord } from "../types/mcpTypes.js";
import type { RunRecord } from "../types/runtimeTypes.js";
import type { TaskRecord } from "../types/taskTypes.js";
import { sdkContextUsagePayload, type SdkContextUsageOptions } from "./sdkContextUsage.js";
import { SdkFileReadStates, type SdkReadStateSeedOptions } from "./sdkFileReadStates.js";
import { rewindSdkFiles } from "./sdkFileRewind.js";
import { createSdkFileHistoryRecorder, type SdkFileHistoryRecorder } from "./sdkFileHistoryRecorder.js";
import { SdkMessageQueue } from "./sdkMessageQueue.js";
import { SdkProtocolRunner, type SdkProtocolRunnerOptions } from "./sdkProtocolRunner.js";
import { runSdkJsonlChunks } from "./sdkJsonlChunkRunner.js";
import { defaultSdkControlResponsePayload } from "./sdkControlHandlers.js";
import {
  chatPayloadFromSdkOptions,
  type SdkQueryOptions
} from "./sdkTypes.js";
import type { SdkMessage, SdkResultMessage, SdkUserMessage } from "./sdkMessages.js";
import { sdkMessagesFromRuntimeEvent } from "./sdkEventProjection.js";
import { sdkResultMessageFromAgentResult } from "./sdkResultMessages.js";
import {
  getSdkSessionInfo,
  getSdkSessionMessages,
  listSdkSessionRuns,
  listSdkSessions,
  type SdkGetSessionMessagesOptions,
  type SdkListSessionsOptions,
  type SdkSessionInfo
} from "./sdkSessionRecords.js";
import {
  forkSdkSession,
  renameSdkSession,
  tagSdkSession,
  type SdkForkSessionOptions,
  type SdkForkSessionResult
} from "./sdkSessionMutations.js";
import { SdkSession } from "./sdkSession.js";
import type { SdkJsonlTransport } from "./sdkJsonlTransport.js";
import type { SdkJsonlChunk } from "./sdkJsonl.js";
import type {
  SdkControlRequestMessage,
  SdkControlResponseMessage,
  SdkElicitationHandler,
  SdkElicitationRequest,
  SdkElicitationResponse,
  SdkHookCallbackHandler,
  SdkHookCallbackRequest,
  SdkMcpMessageHandler,
  SdkWireInputMessage,
  SdkWireMessage
} from "./sdkControlTypes.js";
import {
  createSdkControlErrorResponse,
  createSdkControlSuccessResponse
} from "./sdkControlTypes.js";
import { SdkStructuredIo } from "./sdkStructuredIo.js";
import { validateSdkControlRequest } from "./sdkWireValidation.js";
import { SdkActiveTurns, type SdkTurnInterruptTarget } from "./sdkActiveTurns.js";
import { runtimeEventFromSdkUserMessage } from "./sdkUserMessages.js";
import { newSdkUserMessageUuid } from "./sdkUserMessageIds.js";
import {
  normalizeSdkElicitationResponse,
  sdkElicitationRequestFromMcpParams
} from "./sdkMcpElicitations.js";
import {
  SdkAsyncMessageQueue,
  sdkAsyncUserMessage,
  type SdkAsyncMessageInput,
  type SdkAsyncMessageOptions
} from "./sdkAsyncMessages.js";

export type AgentSdkClientOptions = Partial<Omit<AgentRunServiceOptions, "settings" | "store">> & {
  settings: Settings;
  store: JsonStateStore;
  runs?: AgentRunService;
};

export type SdkApprovalResumeOptions = {
  sessionId?: string;
};

export type SdkRewindFilesOptions = {
  sessionId?: string;
  dryRun?: boolean;
};

export class AgentSdkClient {
  private readonly runs: AgentRunService;
  private readonly transientRunSpecs = new Map<string, AgentSpec>();
  private readonly sdkMcpHandlers = new Map<string, SdkMcpMessageHandler>();
  private readonly hookCallbackHandlers = new Map<string, SdkHookCallbackHandler>();
  private readonly activeTurns = new SdkActiveTurns();
  private readonly asyncMessages = new SdkAsyncMessageQueue();
  private readonly fileReadStates = new SdkFileReadStates();
  private elicitationHandler: SdkElicitationHandler | undefined;

  constructor(private readonly options: AgentSdkClientOptions) {
    this.runs = options.runs || new AgentRunService(options);
  }

  get settings(): Settings {
    return this.options.settings;
  }

  static async create(repoRoot = process.cwd()): Promise<AgentSdkClient> {
    const settings = await loadSettings(repoRoot);
    return new AgentSdkClient({
      settings,
      store: new JsonStateStore(statePath(settings.repoRoot, settings.agent.statePath))
    });
  }

  createSession(options: SdkQueryOptions = {}): SdkSession {
    return new SdkSession(this, sdkSessionIdFromOptions(options) || newSdkSessionId(), options);
  }

  create_sdk_session(options: SdkQueryOptions = {}): SdkSession {
    return this.createSession(options);
  }

  async resumeSession(sessionId: string, options: SdkQueryOptions = {}): Promise<SdkSession> {
    const resolvedSessionId = sessionId.trim();
    const info = resolvedSessionId ? await this.getSessionInfo(resolvedSessionId) : undefined;
    if (!info) throw new Error(`session not found: ${sessionId}`);
    return this.createSession({ ...options, sessionId: resolvedSessionId });
  }

  resume_session(sessionId: string, options: SdkQueryOptions = {}): Promise<SdkSession> {
    return this.resumeSession(sessionId, options);
  }

  listSessions(options: SdkListSessionsOptions = {}): Promise<SdkSessionInfo[]> {
    return listSdkSessions(this.options.store, options);
  }

  list_sessions(options: SdkListSessionsOptions = {}): Promise<SdkSessionInfo[]> {
    return this.listSessions(options);
  }

  getSessionInfo(sessionId: string): Promise<SdkSessionInfo | undefined> {
    return getSdkSessionInfo(this.options.store, sessionId);
  }

  get_session_info(sessionId: string): Promise<SdkSessionInfo | undefined> {
    return this.getSessionInfo(sessionId);
  }

  getSessionMessages(sessionId: string, options: SdkGetSessionMessagesOptions = {}): Promise<SdkMessage[]> {
    return getSdkSessionMessages(this.options.store, sessionId, options);
  }

  get_session_messages(sessionId: string, options: SdkGetSessionMessagesOptions = {}): Promise<SdkMessage[]> {
    return this.getSessionMessages(sessionId, options);
  }

  async renameSession(sessionId: string, title: string): Promise<void> {
    await renameSdkSession(this.options.store, sessionId, title);
  }

  rename_session(sessionId: string, title: string): Promise<void> {
    return this.renameSession(sessionId, title);
  }

  async tagSession(sessionId: string, tag: string | undefined): Promise<void> {
    await tagSdkSession(this.options.store, sessionId, tag);
  }

  tag_session(sessionId: string, tag: string | undefined): Promise<void> {
    return this.tagSession(sessionId, tag);
  }

  forkSession(sessionId: string, options: SdkForkSessionOptions = {}): Promise<SdkForkSessionResult> {
    return forkSdkSession(this.options.store, sessionId, options);
  }

  fork_session(sessionId: string, options: SdkForkSessionOptions = {}): Promise<SdkForkSessionResult> {
    return this.forkSession(sessionId, options);
  }

  getContextUsage(options: SdkContextUsageOptions = {}): Promise<Record<string, unknown>> {
    return sdkContextUsagePayload({
      settings: this.settings,
      store: this.options.store,
      options
    });
  }

  listMcpServers(filters: StoreScopeFilter = {}): Promise<McpServerRecord[]> {
    return this.options.store.listMcpServers(filters);
  }

  saveMcpServer(record: McpServerRecord): Promise<McpServerRecord> {
    return this.options.store.saveMcpServer(record);
  }

  deleteMcpServer(name: string, filters: StoreScopeFilter = {}): Promise<boolean> {
    return this.options.store.deleteMcpServer(name, filters);
  }

  async stopTask(taskId: string, scope: StoreScopeFilter = {}): Promise<TaskRecord> {
    const task = await resolveTaskInScope(this.options.store, taskId, scope);
    const canceledTask = this.options.taskRunner
      ? await this.options.taskRunner.cancel(task.task_id)
      : await new TaskService(this.options.settings, this.options.store).cancel(task.task_id);
    if (isTaskRecord(canceledTask)) return canceledTask;
    return (await this.options.store.loadTask(task.task_id)) || task;
  }

  async seedReadState(requestedPath: string, observedMtime: number, options: SdkReadStateSeedOptions = {}): Promise<Record<string, unknown>> {
    return this.fileReadStates.seedReadState(this.settings.repoRoot, requestedPath, observedMtime, options);
  }

  rewindFiles(userMessageId: string, options: SdkRewindFilesOptions = {}): Promise<Record<string, unknown>> {
    return rewindSdkFiles({
      store: this.options.store,
      repoRoot: this.settings.repoRoot,
      sessionId: options.sessionId || "",
      userMessageId,
      dryRun: options.dryRun
    });
  }

  registerSdkMcpServer(name: string, handler: SdkMcpMessageHandler): void {
    const serverName = name.trim();
    if (!serverName) throw new Error("SDK MCP server name is required");
    this.sdkMcpHandlers.set(serverName, handler);
  }

  register_sdk_mcp_server(name: string, handler: SdkMcpMessageHandler): void {
    this.registerSdkMcpServer(name, handler);
  }

  unregisterSdkMcpServer(name: string): void {
    this.sdkMcpHandlers.delete(name.trim());
  }

  unregister_sdk_mcp_server(name: string): void {
    this.unregisterSdkMcpServer(name);
  }

  listSdkMcpServerNames(): string[] {
    return [...this.sdkMcpHandlers.keys()].sort();
  }

  hasSdkMcpServer(name: string): boolean {
    return this.sdkMcpHandlers.has(name.trim());
  }

  async callSdkMcpServer(name: string, message: unknown): Promise<unknown> {
    const serverName = name.trim();
    const handler = this.sdkMcpHandlers.get(serverName);
    if (!handler) throw new Error(`SDK MCP server not registered: ${serverName}`);
    return handler(message);
  }

  registerHookCallback(callbackId: string, handler: SdkHookCallbackHandler): void {
    const resolvedCallbackId = callbackId.trim();
    if (!resolvedCallbackId) throw new Error("hook callback id is required");
    this.hookCallbackHandlers.set(resolvedCallbackId, handler);
  }

  register_hook_callback(callbackId: string, handler: SdkHookCallbackHandler): void {
    this.registerHookCallback(callbackId, handler);
  }

  unregisterHookCallback(callbackId: string): void {
    this.hookCallbackHandlers.delete(callbackId.trim());
  }

  unregister_hook_callback(callbackId: string): void {
    this.unregisterHookCallback(callbackId);
  }

  async callHookCallback(request: SdkHookCallbackRequest): Promise<Record<string, unknown> | undefined> {
    const handler = this.hookCallbackHandlers.get(request.callbackId.trim());
    return handler?.(request);
  }

  setElicitationHandler(handler: SdkElicitationHandler | undefined): void {
    this.elicitationHandler = handler;
  }

  set_elicitation_handler(handler: SdkElicitationHandler | undefined): void {
    this.setElicitationHandler(handler);
  }

  async runElicitation(request: SdkElicitationRequest): Promise<SdkElicitationResponse | undefined> {
    return this.elicitationHandler?.(request);
  }

  async handleMcpElicitation(serverName: string, params: unknown): Promise<Record<string, unknown>> {
    const request = sdkElicitationRequestFromMcpParams(serverName, params);
    return normalizeSdkElicitationResponse(await this.runElicitation(request));
  }

  async handleControlRequest(
    message: SdkControlRequestMessage | Record<string, unknown>,
    options: SdkProtocolRunnerOptions = {}
  ): Promise<SdkControlResponseMessage> {
    const controlRequest = sdkControlRequestMessage(message);
    const providedStructuredIo = options.structuredIo ?? options.structured_io;
    const structuredIo = providedStructuredIo || new SdkStructuredIo();
    try {
      const payload = await defaultSdkControlResponsePayload(controlRequest, {
        client: this,
        options,
        structuredIo
      });
      return createSdkControlSuccessResponse(controlRequest.requestId, payload);
    } catch (error) {
      return createSdkControlErrorResponse(controlRequest.requestId, errorMessage(error));
    } finally {
      if (!providedStructuredIo) structuredIo.close();
    }
  }

  interruptActiveTurn(target: SdkTurnInterruptTarget = {}): Record<string, unknown> {
    return this.activeTurns.interrupt(target);
  }

  cancelAsyncMessage(messageUuid: string): Record<string, unknown> {
    const queued = this.asyncMessages.cancel(messageUuid);
    if (queued.length) return { cancelled: true, queued: queued.length };
    return this.activeTurns.cancelAsyncMessage(messageUuid);
  }

  enqueueAsyncMessage(message: SdkAsyncMessageInput, options: SdkAsyncMessageOptions = {}): SdkUserMessage {
    const queued = this.asyncMessages.enqueue(message, options);
    this.activeTurns.wake({ sessionId: queued.sessionId });
    if (queued.priority === "now") this.activeTurns.interrupt({ sessionId: queued.sessionId });
    return queued;
  }

  enqueue_async_message(message: SdkAsyncMessageInput, options: SdkAsyncMessageOptions = {}): SdkUserMessage {
    return this.enqueueAsyncMessage(message, options);
  }

  listAsyncMessages(options: { sessionId?: string; session_id?: string } = {}): SdkUserMessage[] {
    return this.asyncMessages.list(String(options.sessionId || options.session_id || ""));
  }

  list_async_messages(options: { sessionId?: string; session_id?: string } = {}): SdkUserMessage[] {
    return this.listAsyncMessages(options);
  }

  dequeueAsyncMessage(options: { sessionId?: string; session_id?: string } = {}): SdkUserMessage | undefined {
    return this.asyncMessages.dequeue(String(options.sessionId || options.session_id || ""));
  }

  dequeue_async_message(options: { sessionId?: string; session_id?: string } = {}): SdkUserMessage | undefined {
    return this.dequeueAsyncMessage(options);
  }

  async *query(prompt: string, options: SdkQueryOptions = {}): AsyncIterable<SdkMessage> {
    const sessionId = sdkSessionIdFromOptions(options) || newSdkSessionId();
    yield* this.queryUserMessage({
      type: "user_message",
      uuid: newSdkUserMessageUuid(),
      sessionId,
      content: prompt
    }, options);
  }

  async *queryUserMessage(message: SdkAsyncMessageInput, options: SdkQueryOptions = {}): AsyncIterable<SdkMessage> {
    const optionsSessionId = sdkSessionIdFromOptions(options);
    const coercedMessage = sdkAsyncUserMessage(message, { sessionId: optionsSessionId });
    const sessionId = coercedMessage.sessionId || optionsSessionId || newSdkSessionId();
    const userMessage = { ...coercedMessage, sessionId };
    const queue = new SdkMessageQueue<SdkMessage>();
    queue.push(userMessage);

    this.runQuery(userMessage.content, sessionId, options, queue, userMessage).catch((error) => queue.fail(error));
    while (true) {
      const message = await queue.shift();
      if (!message) return;
      yield message;
    }
  }

  query_user_message(message: SdkAsyncMessageInput, options: SdkQueryOptions = {}): AsyncIterable<SdkMessage> {
    return this.queryUserMessage(message, options);
  }

  async prompt(prompt: string, options: SdkQueryOptions = {}): Promise<SdkResultMessage> {
    let result: SdkResultMessage | undefined;
    for await (const message of this.query(prompt, options)) {
      if (message.type === "result") result = message;
    }
    if (!result) throw new Error("SDK query completed without a result message");
    return result;
  }

  async *resumeApproval(runId: string, approved: boolean, options: SdkApprovalResumeOptions = {}): AsyncIterable<SdkMessage> {
    const queue = new SdkMessageQueue<SdkMessage>();
    this.runApprovalResume(runId, approved, options, queue).catch((error) => queue.fail(error));
    while (true) {
      const message = await queue.shift();
      if (!message) return;
      yield message;
    }
  }

  runWireMessages(
    messages: AsyncIterable<SdkWireInputMessage> | Iterable<SdkWireInputMessage>,
    options: SdkProtocolRunnerOptions = {}
  ): AsyncIterable<SdkWireMessage> {
    return new SdkProtocolRunner(this, options).runMessages(messages);
  }

  runStdin(
    messages: AsyncIterable<SdkWireInputMessage> | Iterable<SdkWireInputMessage>,
    options: SdkProtocolRunnerOptions = {}
  ): AsyncIterable<SdkWireMessage> {
    return this.runWireMessages(messages, options);
  }

  run_stdin(
    messages: AsyncIterable<SdkWireInputMessage> | Iterable<SdkWireInputMessage>,
    options: SdkProtocolRunnerOptions = {}
  ): AsyncIterable<SdkWireMessage> {
    return this.runStdin(messages, options);
  }

  runJsonlTransport(transport: SdkJsonlTransport, options: SdkProtocolRunnerOptions = {}): Promise<void> {
    return new SdkProtocolRunner(this, options).runJsonlTransport(transport);
  }

  run_jsonl_transport(transport: SdkJsonlTransport, options: SdkProtocolRunnerOptions = {}): Promise<void> {
    return this.runJsonlTransport(transport, options);
  }

  runJsonlChunks(
    chunks: AsyncIterable<SdkJsonlChunk> | Iterable<SdkJsonlChunk>,
    options: SdkProtocolRunnerOptions = {}
  ): AsyncIterable<string> {
    return runSdkJsonlChunks(chunks, (messages, runnerOptions) => this.runWireMessages(messages, runnerOptions), options);
  }

  runStdinJsonl(
    chunks: AsyncIterable<SdkJsonlChunk> | Iterable<SdkJsonlChunk>,
    options: SdkProtocolRunnerOptions = {}
  ): AsyncIterable<string> {
    return this.runJsonlChunks(chunks, options);
  }

  run_stdin_jsonl(
    chunks: AsyncIterable<SdkJsonlChunk> | Iterable<SdkJsonlChunk>,
    options: SdkProtocolRunnerOptions = {}
  ): AsyncIterable<string> {
    return this.runStdinJsonl(chunks, options);
  }

  private async runQuery(
    prompt: string,
    sessionId: string,
    options: SdkQueryOptions,
    queue: SdkMessageQueue<SdkMessage>,
    userMessage: SdkUserMessage
  ): Promise<void> {
    const userMessageUuid = userMessage.uuid;
    let activeRunId = "";
    let fileHistory: SdkFileHistoryRecorder | undefined;
    let projectedResult = false;
    const activeTurn = this.activeTurns.start({
      sessionId,
      userMessageUuid,
      isWakeRequested: () => this.asyncMessages.has({ sessionId, maxPriority: "later" })
    });
    const payload = chatPayloadFromSdkOptions(prompt, {
      ...options,
      sessionId,
      metadata: {
        ...(options.metadata || {}),
        ...(userMessageUuid ? { sdk_user_message_uuid: userMessageUuid } : {})
      }
    });
    const spec = this.runs.specFromPayload(payload);
    try {
      const { run, result } = await this.runs.runAgent(spec, payload.message, {
        stream: true,
        signal: activeTurn.signal,
        sleepWake: activeTurn.sleepWake,
        fileReadState: this.fileReadStates.forSession(sessionId),
        afterRunStarted: async (startedRun) => {
          activeRunId = startedRun.run_id;
          activeTurn.bindRunId(startedRun.run_id);
          this.transientRunSpecs.set(startedRun.run_id, spec);
          const userEvent = runtimeEventFromSdkUserMessage(userMessage, {
            runId: startedRun.run_id,
            sessionId,
            prompt
          });
          await this.options.store.recordEvent(startedRun.run_id, userEvent);
          fileHistory = await createSdkFileHistoryRecorder({
            repoRoot: this.settings.repoRoot,
            sessionId,
            messageId: userMessageUuid,
            metadata: payload.metadata,
            runs: await listSdkSessionRuns(this.options.store, sessionId)
          });
          if (fileHistory) await this.options.store.recordEvent(startedRun.run_id, fileHistory.initialEvent());
          queue.push(runStartedMessage(startedRun, sessionId));
        },
        onEvent: async (event) => {
          for (const message of sdkMessagesFromRuntimeEvent(activeRunId, sessionId, event)) {
            if (message.type === "result") projectedResult = true;
            queue.push(message);
          }
          if (!fileHistory) return;
          for (const snapshotEvent of await fileHistory.observe(event)) {
            await this.options.store.recordEvent(activeRunId, snapshotEvent);
          }
        }
      });
      if (!projectedResult) queue.push(sdkResultMessageFromAgentResult(run.run_id, sessionId, result));
      if (result.status !== "awaiting_approval") this.transientRunSpecs.delete(run.run_id);
    } finally {
      activeTurn.finish();
      queue.close();
    }
  }

  private async runApprovalResume(
    runId: string,
    approved: boolean,
    options: SdkApprovalResumeOptions,
    queue: SdkMessageQueue<SdkMessage>
  ): Promise<void> {
    const existingRun = await this.options.store.loadRun(runId);
    const sessionId = options.sessionId || existingRun?.metadata.sdk_session_id || "";
    let projectedResult = false;
    const { run, result } = await this.runs.resumeApproval(runId, approved, {
      spec: this.transientRunSpecs.get(runId),
      stream: true,
      fileReadState: sessionId ? this.fileReadStates.forSession(sessionId) : undefined,
      onEvent: (event) => {
        for (const message of sdkMessagesFromRuntimeEvent(runId, sessionId, event)) {
          if (message.type === "result") projectedResult = true;
          queue.push(message);
        }
      }
    });
    if (result.status !== "awaiting_approval") this.transientRunSpecs.delete(runId);
    if (!projectedResult) {
      queue.push(sdkResultMessageFromAgentResult(run.run_id, sessionId || run.metadata.sdk_session_id || "", result));
    }
    queue.close();
  }
}

function runStartedMessage(run: RunRecord, sessionId: string): SdkMessage {
  return {
    type: "run_started",
    runId: run.run_id,
    sessionId,
    createdAt: run.created_at
  };
}

function newSdkSessionId(): string {
  return `session_${crypto.randomUUID().replaceAll("-", "")}`;
}

function sdkSessionIdFromOptions(options: SdkQueryOptions): string {
  return String(options.sessionId || options.session_id || "").trim();
}

function sdkControlRequestMessage(message: SdkControlRequestMessage | Record<string, unknown>): SdkControlRequestMessage {
  return validateSdkControlRequest(message);
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function isTaskRecord(value: unknown): value is TaskRecord {
  return Boolean(value)
    && typeof value === "object"
    && typeof (value as TaskRecord).task_id === "string"
    && typeof (value as TaskRecord).status === "string";
}
