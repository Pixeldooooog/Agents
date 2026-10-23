import {
  createSdkControlCancelRequest,
  createSdkControlRequest,
  isSdkControlResponse,
  isSdkPermissionControlRequest,
  type SdkControlRequestMessage,
  type SdkControlRequestPayload,
  type SdkControlResponseMessage,
  type SdkStdinMessage,
  type SdkStdoutMessage,
  type SdkWireMessage
} from "./sdkControlTypes.js";
import { SdkMessageQueue } from "./sdkMessageQueue.js";
import { validateSdkStdinMessage, validateSdkStdoutMessage } from "./sdkWireValidation.js";

const MAX_RESOLVED_TOOL_USE_IDS = 1000;

export type SdkControlResponseValidator<T> = (payload: Record<string, unknown>) => T;
export type SdkUnexpectedResponseHandler = (response: SdkControlResponseMessage) => void | Promise<void>;
export type SdkControlRequestSentHandler = (request: SdkControlRequestMessage) => void | Promise<void>;
export type SdkControlRequestResolvedHandler = (requestId: string) => void | Promise<void>;

export type SdkStructuredIoOptions = {
  replayControlResponses?: boolean;
  replay_control_responses?: boolean;
  replayUserMessages?: boolean;
  replay_user_messages?: boolean;
  onUnexpectedResponse?: SdkUnexpectedResponseHandler;
  on_unexpected_response?: SdkUnexpectedResponseHandler;
  onControlRequestSent?: SdkControlRequestSentHandler;
  on_control_request_sent?: SdkControlRequestSentHandler;
  onControlRequestResolved?: SdkControlRequestResolvedHandler;
  on_control_request_resolved?: SdkControlRequestResolvedHandler;
};

export type SdkSendControlRequestOptions<T> = {
  requestId?: string;
  request_id?: string;
  responseValidator?: SdkControlResponseValidator<T>;
  response_validator?: SdkControlResponseValidator<T>;
};

type PendingControlRequest<T = unknown> = {
  request: SdkControlRequestMessage;
  resolve: (payload: T) => void;
  reject: (error: unknown) => void;
  responseValidator?: SdkControlResponseValidator<T>;
};

export class SdkControlStreamClosedError extends Error {
  constructor(message = "SDK structured IO stream is closed") {
    super(message);
    this.name = "SdkControlStreamClosedError";
  }
}

export class SdkControlRequestCancelledError extends Error {
  constructor(message = "SDK control request canceled") {
    super(message);
    this.name = "SdkControlRequestCancelledError";
  }
}

export class SdkControlRequestError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SdkControlRequestError";
  }
}

export class SdkStructuredIo {
  private readonly outbound = new SdkMessageQueue<SdkStdoutMessage>();
  private readonly pendingRequests = new Map<string, PendingControlRequest>();
  private readonly resolvedToolUseIds = new Set<string>();
  private readonly resolvedToolUseOrder: string[] = [];
  private readonly options: SdkStructuredIoOptions;
  private closedState = false;

  constructor(options: SdkStructuredIoOptions = {}) {
    this.options = normalizeStructuredIoOptions(options);
  }

  get isClosed(): boolean {
    return this.closedState;
  }

  get closed(): boolean {
    return this.closedState;
  }

  get pendingCount(): number {
    return this.pendingRequests.size;
  }

  get pending_count(): number {
    return this.pendingCount;
  }

  get replayUserMessages(): boolean {
    return Boolean(this.options.replayUserMessages);
  }

  set replayUserMessages(enabled: boolean) {
    this.options.replayUserMessages = enabled;
  }

  get replay_user_messages(): boolean {
    return this.replayUserMessages;
  }

  set replay_user_messages(enabled: boolean) {
    this.replayUserMessages = enabled;
  }

  setReplayControlResponses(enabled: boolean): void {
    this.options.replayControlResponses = enabled;
    this.options.replayUserMessages = enabled;
  }

  set_replay_control_responses(enabled: boolean): void {
    this.setReplayControlResponses(enabled);
  }

  setUnexpectedResponseHandler(handler: SdkUnexpectedResponseHandler | undefined): void {
    this.options.onUnexpectedResponse = handler;
  }

  set_unexpected_response_handler(handler: SdkUnexpectedResponseHandler | undefined): void {
    this.setUnexpectedResponseHandler(handler);
  }

  setOnControlRequestSent(handler: SdkControlRequestSentHandler | undefined): void {
    this.options.onControlRequestSent = handler;
  }

  set_on_control_request_sent(handler: SdkControlRequestSentHandler | undefined): void {
    this.setOnControlRequestSent(handler);
  }

  setOnControlRequestResolved(handler: SdkControlRequestResolvedHandler | undefined): void {
    this.options.onControlRequestResolved = handler;
  }

  set_on_control_request_resolved(handler: SdkControlRequestResolvedHandler | undefined): void {
    this.setOnControlRequestResolved(handler);
  }

  getPendingPermissionRequests(): SdkControlRequestMessage[] {
    return [...this.pendingRequests.values()]
      .map((pending) => pending.request)
      .filter(isSdkPermissionControlRequest);
  }

  get_pending_permission_requests(): SdkControlRequestMessage[] {
    return this.getPendingPermissionRequests();
  }

  write(message: SdkWireMessage): void {
    this.assertOpen();
    this.outbound.push(validateSdkStdoutMessage(message));
  }

  nextOutboundMessage(): Promise<SdkStdoutMessage | undefined> {
    return this.outbound.shift();
  }

  nextStdoutMessage(): Promise<SdkStdoutMessage | undefined> {
    return this.nextOutboundMessage();
  }

  next_stdout_message(): Promise<SdkStdoutMessage | undefined> {
    return this.nextStdoutMessage();
  }

  drainOutboundMessages(): SdkStdoutMessage[] {
    return this.outbound.drain();
  }

  drainStdoutMessages(): SdkStdoutMessage[] {
    return this.drainOutboundMessages();
  }

  drain_stdout_messages(): SdkStdoutMessage[] {
    return this.drainStdoutMessages();
  }

  async sendRequest<T = Record<string, unknown>>(
    request: SdkControlRequestPayload,
    options: SdkSendControlRequestOptions<T> = {}
  ): Promise<T> {
    this.assertOpen();
    const controlRequest = createSdkControlRequest(request, options.requestId ?? options.request_id);
    const responseValidator = options.responseValidator ?? options.response_validator;
    const result = new Promise<T>((resolve, reject) => {
      this.pendingRequests.set(controlRequest.requestId, {
        request: controlRequest,
        resolve: resolve as (payload: unknown) => void,
        reject,
        responseValidator
      });
    });
    this.write(controlRequest);
    if (isSdkPermissionControlRequest(controlRequest)) {
      this.invokeHandler(this.options.onControlRequestSent, controlRequest);
    }
    return result.finally(() => this.pendingRequests.delete(controlRequest.requestId));
  }

  send_request<T = Record<string, unknown>>(
    request: SdkControlRequestPayload,
    options: SdkSendControlRequestOptions<T> = {}
  ): Promise<T> {
    return this.sendRequest(request, options);
  }

  async cancelRequest(requestId: string): Promise<void> {
    this.assertOpen();
    const pending = this.pendingRequests.get(requestId);
    this.write(createSdkControlCancelRequest(requestId));
    if (!pending) return;
    this.trackResolvedPermissionRequest(pending.request);
    pending.reject(new SdkControlRequestCancelledError());
  }

  cancel_request(requestId: string): Promise<void> {
    return this.cancelRequest(requestId);
  }

  async injectControlResponse(response: SdkWireMessage): Promise<void> {
    const controlResponse = validateSdkStdinMessage(response);
    if (!isSdkControlResponse(controlResponse)) {
      throw new Error("injectControlResponse expects a control_response message");
    }
    const pending = this.pendingRequests.get(controlResponse.response.requestId);
    if (!pending) return;
    this.trackResolvedPermissionRequest(pending.request);
    this.write(createSdkControlCancelRequest(controlResponse.response.requestId));
    await this.resolvePendingRequest(pending, controlResponse);
  }

  inject_control_response(response: SdkWireMessage): Promise<void> {
    return this.injectControlResponse(response);
  }

  async receive(message: SdkWireMessage): Promise<SdkStdinMessage | undefined> {
    const inbound = validateSdkStdinMessage(message);
    if (!isSdkControlResponse(inbound)) return inbound;

    const pending = this.pendingRequests.get(inbound.response.requestId);
    if (!pending) {
      if (this.isDuplicateResolvedToolResponse(inbound)) return undefined;
      this.invokeHandler(this.options.onUnexpectedResponse, inbound);
      return this.shouldReplayControlResponses() ? inbound : undefined;
    }

    this.trackResolvedPermissionRequest(pending.request);
    this.pendingRequests.delete(inbound.response.requestId);
    if (isSdkPermissionControlRequest(pending.request)) {
      this.invokeHandler(this.options.onControlRequestResolved, inbound.response.requestId);
    }
    await this.resolvePendingRequest(pending, inbound);
    return this.shouldReplayControlResponses() ? inbound : undefined;
  }

  close(): void {
    if (this.closedState) return;
    this.closedState = true;
    for (const pending of this.pendingRequests.values()) {
      pending.reject(new SdkControlStreamClosedError("SDK structured IO stream closed before response received"));
    }
    this.pendingRequests.clear();
    this.outbound.close();
  }

  private async resolvePendingRequest(
    pending: PendingControlRequest,
    response: SdkControlResponseMessage
  ): Promise<void> {
    if (response.response.subtype === "error") {
      pending.reject(new SdkControlRequestError(response.response.error));
      return;
    }
    const payload = response.response.response || {};
    try {
      pending.resolve(pending.responseValidator ? pending.responseValidator(payload) : payload);
    } catch (error) {
      pending.reject(error);
    }
  }

  private trackResolvedPermissionRequest(request: SdkControlRequestMessage): void {
    if (request.request.subtype !== "can_use_tool") return;
    const toolUseId = request.request.toolUseId;
    if (this.resolvedToolUseIds.has(toolUseId)) return;
    this.resolvedToolUseIds.add(toolUseId);
    this.resolvedToolUseOrder.push(toolUseId);
    while (this.resolvedToolUseOrder.length > MAX_RESOLVED_TOOL_USE_IDS) {
      const expiredToolUseId = this.resolvedToolUseOrder.shift();
      if (expiredToolUseId) this.resolvedToolUseIds.delete(expiredToolUseId);
    }
  }

  private isDuplicateResolvedToolResponse(response: SdkControlResponseMessage): boolean {
    if (response.response.subtype !== "success") return false;
    const payload = response.response.response || {};
    const toolUseId = payload.toolUseId ?? payload.toolUseID ?? payload.tool_use_id;
    return typeof toolUseId === "string" && this.resolvedToolUseIds.has(toolUseId);
  }

  private shouldReplayControlResponses(): boolean {
    return Boolean(this.options.replayControlResponses ?? this.options.replayUserMessages);
  }

  private assertOpen(): void {
    if (this.closedState) throw new SdkControlStreamClosedError();
  }

  private invokeHandler<T>(handler: ((value: T) => void | Promise<void>) | undefined, value: T): void {
    if (!handler) return;
    try {
      void Promise.resolve(handler(value)).catch(() => undefined);
    } catch {
      // Control handlers are observability hooks; they must not stall protocol flow.
    }
  }
}

function normalizeStructuredIoOptions(options: SdkStructuredIoOptions): SdkStructuredIoOptions {
  return {
    ...options,
    replayControlResponses: options.replayControlResponses ?? options.replay_control_responses,
    replayUserMessages: options.replayUserMessages ?? options.replay_user_messages,
    onUnexpectedResponse: options.onUnexpectedResponse ?? options.on_unexpected_response,
    onControlRequestSent: options.onControlRequestSent ?? options.on_control_request_sent,
    onControlRequestResolved: options.onControlRequestResolved ?? options.on_control_request_resolved
  };
}
