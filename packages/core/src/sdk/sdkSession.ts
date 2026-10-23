import type { AgentSdkClient } from "./agentSdkClient.js";
import type { SdkContextUsageOptions } from "./sdkContextUsage.js";
import type { SdkMessage, SdkResultMessage, SdkUserMessage } from "./sdkMessages.js";
import type { SdkQueryOptions } from "./sdkTypes.js";
import type { SdkAsyncMessageInput, SdkAsyncMessageOptions, SdkAsyncMessagePriority } from "./sdkAsyncMessages.js";
import type { SdkGetSessionMessagesOptions, SdkSessionInfo } from "./sdkSessionRecords.js";
import type { SdkForkSessionOptions } from "./sdkSessionMutations.js";
import type { SdkProtocolRunnerOptions } from "./sdkProtocolRunner.js";
import type { SdkJsonlTransport } from "./sdkJsonlTransport.js";
import type { SdkJsonlChunk } from "./sdkJsonl.js";
import type { SdkControlRequestMessage, SdkControlResponseMessage, SdkWireInputMessage, SdkWireMessage } from "./sdkControlTypes.js";

export class SdkSession {
  constructor(
    private readonly client: AgentSdkClient,
    readonly sessionId: string,
    private defaults: SdkProtocolRunnerOptions = {}
  ) {}

  get session_id(): string {
    return this.sessionId;
  }

  get options(): SdkProtocolRunnerOptions {
    const options = this.optionsForQuery({} as SdkProtocolRunnerOptions);
    return { ...options, session_id: this.sessionId };
  }

  async *query(prompt: string, options: SdkQueryOptions = {}): AsyncIterable<SdkMessage> {
    const queryOptions = this.optionsForQuery(options);
    let lastResult: SdkResultMessage | undefined;
    for await (const message of this.client.query(prompt, queryOptions)) {
      if (message.type === "result") lastResult = message;
      yield message;
    }
    if (lastResult?.status === "awaiting_approval") return;
    yield* this.drainAsyncMessages(queryOptions);
  }

  async prompt(prompt: string, options: SdkQueryOptions = {}): Promise<SdkResultMessage> {
    let result: SdkResultMessage | undefined;
    for await (const message of this.query(prompt, options)) {
      if (message.type === "result") result = message;
    }
    if (!result) throw new Error("SDK session prompt completed without a result message");
    return result;
  }

  resumeApproval(runId: string, approved: boolean): AsyncIterable<SdkMessage> {
    return this.client.resumeApproval(runId, approved, { sessionId: this.sessionId });
  }

  runWireMessages(
    messages: AsyncIterable<SdkWireInputMessage> | Iterable<SdkWireInputMessage>,
    options: SdkProtocolRunnerOptions = {}
  ): AsyncIterable<SdkWireMessage> {
    return this.client.runWireMessages(messages, this.optionsForQuery(options));
  }

  runJsonlTransport(transport: SdkJsonlTransport, options: SdkProtocolRunnerOptions = {}): Promise<void> {
    return this.client.runJsonlTransport(transport, this.optionsForQuery(options));
  }

  runJsonlChunks(
    chunks: AsyncIterable<SdkJsonlChunk> | Iterable<SdkJsonlChunk>,
    options: SdkProtocolRunnerOptions = {}
  ): AsyncIterable<string> {
    return this.client.runJsonlChunks(chunks, this.optionsForQuery(options));
  }

  async handleControlRequest(
    message: SdkControlRequestMessage | Record<string, unknown>
  ): Promise<SdkControlResponseMessage> {
    const controlOptions = this.optionsForQuery({} as SdkProtocolRunnerOptions);
    const response = await this.client.handleControlRequest(message, controlOptions);
    if (response.response.subtype === "success") {
      this.defaults = sessionDefaultsFromControlOptions(controlOptions);
    }
    return response;
  }

  handle_control_request(
    message: SdkControlRequestMessage | Record<string, unknown>
  ): Promise<SdkControlResponseMessage> {
    return this.handleControlRequest(message);
  }

  messages(options: SdkGetSessionMessagesOptions = {}): Promise<SdkMessage[]> {
    return this.client.getSessionMessages(this.sessionId, options);
  }

  info(): Promise<SdkSessionInfo | undefined> {
    return this.client.getSessionInfo(this.sessionId);
  }

  async rename(title: string): Promise<void> {
    await this.client.renameSession(this.sessionId, title);
  }

  async tag(tag: string | undefined): Promise<void> {
    await this.client.tagSession(this.sessionId, tag);
  }

  async fork(options: SdkForkSessionOptions = {}): Promise<SdkSession> {
    const result = await this.client.forkSession(this.sessionId, options);
    return this.client.createSession({ ...sessionDefaultsFromControlOptions(this.defaults), sessionId: result.sessionId });
  }

  enqueueAsyncMessage(message: SdkAsyncMessageInput, priority?: SdkAsyncMessagePriority): SdkUserMessage {
    return this.client.enqueueAsyncMessage(message, { sessionId: this.sessionId, priority });
  }

  enqueue_async_message(
    message: SdkAsyncMessageInput,
    options?: SdkAsyncMessagePriority | Pick<SdkAsyncMessageOptions, "priority">
  ): SdkUserMessage {
    const priority = typeof options === "string" ? options : options?.priority;
    return this.enqueueAsyncMessage(message, priority);
  }

  listAsyncMessages(): SdkUserMessage[] {
    return this.client.listAsyncMessages({ sessionId: this.sessionId });
  }

  list_async_messages(): SdkUserMessage[] {
    return this.listAsyncMessages();
  }

  dequeueAsyncMessage(): SdkUserMessage | undefined {
    return this.client.dequeueAsyncMessage({ sessionId: this.sessionId });
  }

  dequeue_async_message(): SdkUserMessage | undefined {
    return this.dequeueAsyncMessage();
  }

  contextUsage(options: SdkContextUsageOptions = {}): Promise<Record<string, unknown>> {
    return this.client.getContextUsage({
      ...options,
      sessionId: this.sessionId,
      model: options.model || this.defaults.model
    });
  }

  private optionsForQuery<T extends SdkQueryOptions>(options: T): T {
    return {
      ...this.defaults,
      ...options,
      sessionId: this.sessionId,
      metadata: {
        ...(this.defaults.metadata || {}),
        ...(options.metadata || {})
      }
    } as T;
  }

  private async *drainAsyncMessages(options: SdkQueryOptions): AsyncIterable<SdkMessage> {
    while (true) {
      const queued = this.client.dequeueAsyncMessage({ sessionId: this.sessionId });
      if (!queued) return;
      let lastResult: SdkResultMessage | undefined;
      for await (const message of this.client.queryUserMessage(queued, options)) {
        if (message.type === "result") lastResult = message;
        yield message;
      }
      if (lastResult?.status === "awaiting_approval") return;
    }
  }
}

function sessionDefaultsFromControlOptions(options: SdkProtocolRunnerOptions): SdkProtocolRunnerOptions {
  const defaults = { ...options };
  delete defaults.sessionId;
  delete defaults.session_id;
  delete defaults.structuredIo;
  delete defaults.structured_io;
  delete defaults.closeTransport;
  delete defaults.close_transport;
  delete defaults.controlHandler;
  return defaults;
}
