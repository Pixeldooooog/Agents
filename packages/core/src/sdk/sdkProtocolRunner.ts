import type { AgentSdkClient } from "./agentSdkClient.js";
import {
  createSdkControlErrorResponse,
  createSdkControlSuccessResponse,
  type SdkControlRequestMessage,
  type SdkControlResponseMessage,
  type SdkPermissionModeInput,
  type SdkWireInputMessage,
  type SdkWireMessage
} from "./sdkControlTypes.js";
import { type SdkJsonlTransport } from "./sdkJsonlTransport.js";
import { SdkJsonlTransportRunner } from "./sdkJsonlTransportRunner.js";
import { SdkMessageQueue } from "./sdkMessageQueue.js";
import { sdkReplayUserMessagesOption } from "./sdkReplayOptions.js";
import { SdkStructuredIo, type SdkStructuredIoOptions } from "./sdkStructuredIo.js";
import { validateSdkStdinMessage } from "./sdkWireValidation.js";
import { defaultSdkControlResponsePayload } from "./sdkControlHandlers.js";
import type { SdkUserMessage } from "./sdkMessages.js";
import type { SdkQueryOptions } from "./sdkTypes.js";
import { applySdkEnvironmentVariablesUpdate } from "./sdkEnvironmentVariables.js";

export type SdkControlRequestHandlerContext = {
  client: AgentSdkClient;
  options: SdkProtocolRunnerOptions;
  structuredIo: SdkStructuredIo;
};

export type SdkControlRequestHandler = (
  request: SdkControlRequestMessage,
  context: SdkControlRequestHandlerContext
) => Promise<Record<string, unknown> | SdkControlResponseMessage> | Record<string, unknown> | SdkControlResponseMessage;

export type SdkProtocolRunnerOptions = SdkQueryOptions & {
  structuredIo?: SdkStructuredIo;
  structured_io?: SdkStructuredIo;
  closeTransport?: boolean;
  close_transport?: boolean;
  controlHandler?: SdkControlRequestHandler;
  permissionMode?: SdkPermissionModeInput;
  flagSettings?: Record<string, unknown>;
};

export class SdkProtocolRunner {
  constructor(
    private readonly client: AgentSdkClient,
    private readonly defaults: SdkProtocolRunnerOptions = {}
  ) {}

  async *runMessages(
    messages: AsyncIterable<SdkWireInputMessage> | Iterable<SdkWireInputMessage>,
    options: SdkProtocolRunnerOptions = {}
  ): AsyncIterable<SdkWireMessage> {
    const effectiveOptions = mergeProtocolOptions(this.defaults, options);
    const structuredIo = structuredIoForProtocolOptions(effectiveOptions);
    const outputMessages = new SdkMessageQueue<SdkWireMessage>();
    const producer = this.produceWireMessages(messages, effectiveOptions, structuredIo, outputMessages)
      .catch((error) => {
        structuredIo.close();
        outputMessages.fail(error);
      });
    const outboundPump = this.pumpStructuredIoOutbound(structuredIo, outputMessages)
      .catch((error) => {
        structuredIo.close();
        outputMessages.fail(error);
      });
    Promise.allSettled([producer, outboundPump]).then(() => outputMessages.close());
    while (true) {
      const output = await outputMessages.shift();
      if (!output) break;
      yield output;
    }
    await producer;
    await outboundPump;
  }

  async runJsonlTransport(
    transport: SdkJsonlTransport,
    options: SdkProtocolRunnerOptions = {}
  ): Promise<void> {
    const effectiveOptions = mergeProtocolOptions(this.defaults, options);
    const structuredIo = structuredIoForProtocolOptions(effectiveOptions);
    const runner = new SdkJsonlTransportRunner(transport, {
      structuredIo,
      closeTransport: effectiveOptions.closeTransport,
      closeTransportOnInputEnd: false,
      closeStructuredIoOnInputEnd: false
    });
    try {
      const activeUserMessageRuns = new Set<Promise<void>>();
      const receivedUserMessageUuids = new Set<string>();
      for await (const inboundMessage of runner.messages()) {
        if (inboundMessage.type === "user_message") {
          const run = this.emitUserMessageOutputs(
            inboundMessage,
            effectiveOptions,
            receivedUserMessageUuids,
            (output) => runner.structuredIo.write(output)
          )
            .finally(() => activeUserMessageRuns.delete(run));
          activeUserMessageRuns.add(run);
          continue;
        }
        for await (const output of this.processWireMessage(inboundMessage, effectiveOptions, runner.structuredIo)) {
          runner.structuredIo.write(output);
        }
      }
      await Promise.all(activeUserMessageRuns);
    } finally {
      await runner.close();
    }
  }

  private async *processWireMessage(
    message: SdkWireMessage,
    options: SdkProtocolRunnerOptions,
    structuredIo: SdkStructuredIo
  ): AsyncIterable<SdkWireMessage> {
    if (message.type === "user_message") {
      for await (const output of this.client.queryUserMessage(message, queryOptionsForUserMessage(options, message))) {
        yield output;
      }
      return;
    }
    if (message.type === "control_request") {
      yield await this.handleControlRequest(message, options, structuredIo);
      return;
    }
    if (message.type === "update_environment_variables") {
      applySdkEnvironmentVariablesUpdate(options, message.variables || {});
      return;
    }
    if (message.type === "control_response") {
      yield message;
      return;
    }
    if (message.type === "keep_alive" || message.type === "control_cancel_request") {
      return;
    }
  }

  private async handleControlRequest(
    request: SdkControlRequestMessage,
    options: SdkProtocolRunnerOptions,
    structuredIo: SdkStructuredIo
  ): Promise<SdkControlResponseMessage> {
    try {
      const handled = await options.controlHandler?.(request, { client: this.client, options, structuredIo });
      if (handled && isControlResponse(handled)) return handled;
      return createSdkControlSuccessResponse(
        request.requestId,
        handled || await defaultSdkControlResponsePayload(request, { client: this.client, options, structuredIo })
      );
    } catch (error) {
      return createSdkControlErrorResponse(request.requestId, errorMessage(error));
    }
  }

  private async produceWireMessages(
    messages: AsyncIterable<SdkWireInputMessage> | Iterable<SdkWireInputMessage>,
    options: SdkProtocolRunnerOptions,
    structuredIo: SdkStructuredIo,
    outputMessages: SdkMessageQueue<SdkWireMessage>
  ): Promise<void> {
    const inboundMessages = new SdkMessageQueue<SdkWireMessage>();
    const reader = this.readStructuredInboundMessages(messages, structuredIo, inboundMessages)
      .catch((error) => {
        inboundMessages.fail(error);
        throw error;
      });
    const activeUserMessageRuns = new Set<Promise<void>>();
    const receivedUserMessageUuids = new Set<string>();
    try {
      while (true) {
        const inboundMessage = await inboundMessages.shift();
        if (!inboundMessage) break;
        if (inboundMessage.type === "user_message") {
          const run = this.emitUserMessageOutputs(
            inboundMessage,
            options,
            receivedUserMessageUuids,
            (output) => outputMessages.push(output)
          )
            .finally(() => activeUserMessageRuns.delete(run));
          activeUserMessageRuns.add(run);
          continue;
        }
        for await (const output of this.processWireMessage(inboundMessage, options, structuredIo)) {
          outputMessages.push(output);
        }
      }
      await reader;
      await Promise.all(activeUserMessageRuns);
    } finally {
      structuredIo.close();
      await Promise.allSettled([reader]);
    }
  }

  private async readStructuredInboundMessages(
    messages: AsyncIterable<SdkWireInputMessage> | Iterable<SdkWireInputMessage>,
    structuredIo: SdkStructuredIo,
    inboundMessages: SdkMessageQueue<SdkWireMessage>
  ): Promise<void> {
    try {
      for await (const message of asyncMessages(messages)) {
        const inboundMessage = await structuredIo.receive(validateSdkStdinMessage(message));
        if (inboundMessage) inboundMessages.push(inboundMessage);
      }
    } finally {
      inboundMessages.close();
    }
  }

  private async pumpStructuredIoOutbound(
    structuredIo: SdkStructuredIo,
    outputMessages: SdkMessageQueue<SdkWireMessage>
  ): Promise<void> {
    while (true) {
      const output = await structuredIo.nextOutboundMessage();
      if (!output) return;
      outputMessages.push(output);
    }
  }

  private async emitUserMessageOutputs(
    message: SdkUserMessage,
    options: SdkProtocolRunnerOptions,
    receivedUserMessageUuids: Set<string>,
    emit: (message: SdkWireMessage) => void
  ): Promise<void> {
    const acknowledgement = userMessageAcknowledgement(message, options);
    if (receivedUserMessageUuids.has(message.uuid)) {
      if (sdkReplayUserMessagesOption(options) === true) emit(acknowledgement);
      return;
    }
    receivedUserMessageUuids.add(message.uuid);

    let acknowledged = false;
    for await (const output of this.client.queryUserMessage(message, queryOptionsForUserMessage(options, message))) {
      if (!acknowledged && output.type === "user_message" && output.uuid === message.uuid) {
        emit(acknowledgement);
        acknowledged = true;
        continue;
      }
      emit(output);
    }
  }
}

function queryOptionsForUserMessage(options: SdkProtocolRunnerOptions, message: { sessionId: string }): SdkQueryOptions {
  return {
    ...options,
    sessionId: message.sessionId || options.sessionId || options.session_id,
    metadata: {
      ...(options.metadata || {})
    }
  };
}

function mergeProtocolOptions(
  defaults: SdkProtocolRunnerOptions,
  options: SdkProtocolRunnerOptions
): SdkProtocolRunnerOptions {
  const structuredIo = options.structuredIo ?? options.structured_io ?? defaults.structuredIo ?? defaults.structured_io;
  const closeTransport = options.closeTransport ?? options.close_transport ?? defaults.closeTransport ?? defaults.close_transport;
  return {
    ...defaults,
    ...options,
    ...(structuredIo ? { structuredIo } : {}),
    ...(closeTransport === undefined ? {} : { closeTransport }),
    flagSettings: {
      ...(defaults.flagSettings || {}),
      ...(options.flagSettings || {})
    },
    metadata: {
      ...(defaults.metadata || {}),
      ...(options.metadata || {})
    }
  };
}

function structuredIoForProtocolOptions(options: SdkProtocolRunnerOptions): SdkStructuredIo {
  const replayUserMessages = sdkReplayUserMessagesOption(options);
  const structuredIo = options.structuredIo || new SdkStructuredIo(structuredIoOptionsForProtocolOptions(replayUserMessages));
  if (options.structuredIo && replayUserMessages !== undefined) structuredIo.setReplayControlResponses(replayUserMessages);
  return structuredIo;
}

function structuredIoOptionsForProtocolOptions(replayUserMessages: boolean | undefined): SdkStructuredIoOptions {
  return replayUserMessages === undefined ? {} : { replayUserMessages };
}

function userMessageAcknowledgement(message: SdkUserMessage, options: SdkProtocolRunnerOptions): SdkUserMessage {
  if (sdkReplayUserMessagesOption(options) !== true) return message;
  return { ...message, isReplay: true };
}

async function* asyncMessages(
  messages: AsyncIterable<SdkWireInputMessage> | Iterable<SdkWireInputMessage>
): AsyncIterable<SdkWireInputMessage> {
  if (Symbol.asyncIterator in messages) {
    for await (const message of messages as AsyncIterable<SdkWireInputMessage>) yield message;
    return;
  }
  for (const message of messages as Iterable<SdkWireInputMessage>) yield message;
}

function isControlResponse(value: Record<string, unknown> | SdkControlResponseMessage): value is SdkControlResponseMessage {
  return value.type === "control_response";
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
