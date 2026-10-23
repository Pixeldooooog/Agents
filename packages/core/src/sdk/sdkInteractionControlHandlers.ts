import type { SdkControlRequestMessage } from "./sdkControlTypes.js";
import { normalizeSdkElicitationResponse } from "./sdkMcpElicitations.js";
import type { SdkControlRequestHandlerContext } from "./sdkProtocolRunner.js";

export async function hookCallbackControlResponsePayload(
  message: SdkControlRequestMessage,
  context: SdkControlRequestHandlerContext
): Promise<Record<string, unknown>> {
  const request = message.request;
  if (request.subtype !== "hook_callback") return {};

  const response = await context.client.callHookCallback(request);
  if (response === undefined) return {};
  if (!isPlainRecord(response)) throw new Error("hook callback handler must return an object");
  return response;
}

export async function elicitationControlResponsePayload(
  message: SdkControlRequestMessage,
  context: SdkControlRequestHandlerContext
): Promise<Record<string, unknown>> {
  const request = message.request;
  if (request.subtype !== "elicitation") return {};

  const response = await context.client.runElicitation(request);
  return normalizeSdkElicitationResponse(response);
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}
