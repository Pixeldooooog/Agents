import type { SdkControlRequestMessage } from "./sdkControlTypes.js";
import { sdkOptionRunId, sdkOptionSessionId } from "./sdkProtocolOptionAccess.js";
import type { SdkControlRequestHandlerContext } from "./sdkProtocolRunner.js";

export function interruptControlResponsePayload(context: SdkControlRequestHandlerContext): Record<string, unknown> {
  return context.client.interruptActiveTurn({
    sessionId: sdkOptionSessionId(context.options),
    runId: sdkOptionRunId(context.options)
  });
}

export function cancelAsyncMessageControlResponsePayload(
  message: SdkControlRequestMessage,
  context: SdkControlRequestHandlerContext
): Record<string, unknown> {
  const request = message.request;
  if (request.subtype !== "cancel_async_message") return {};
  const payload = { ...context.client.cancelAsyncMessage(request.messageUuid) };
  delete payload.queued;
  return payload;
}
