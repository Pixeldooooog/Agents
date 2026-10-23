import type { SdkControlRequestMessage } from "./sdkControlTypes.js";
import { sdkOptionSessionId } from "./sdkProtocolOptionAccess.js";
import type { SdkControlRequestHandlerContext } from "./sdkProtocolRunner.js";

export function rewindFilesControlResponsePayload(
  message: SdkControlRequestMessage,
  context: SdkControlRequestHandlerContext
): Promise<Record<string, unknown>> {
  const request = message.request;
  if (request.subtype !== "rewind_files") return Promise.resolve({});
  return context.client.rewindFiles(request.userMessageId, {
    sessionId: sdkOptionSessionId(context.options),
    dryRun: request.dryRun ?? undefined
  });
}

export function seedReadStateControlResponsePayload(
  message: SdkControlRequestMessage,
  context: SdkControlRequestHandlerContext
): Promise<Record<string, unknown>> {
  const request = message.request;
  if (request.subtype !== "seed_read_state") return Promise.resolve({});
  return context.client.seedReadState(request.path, request.mtime, {
    sessionId: sdkOptionSessionId(context.options)
  });
}
