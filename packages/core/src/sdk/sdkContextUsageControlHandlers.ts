import { sdkOptionSessionId } from "./sdkProtocolOptionAccess.js";
import type { SdkControlRequestHandlerContext } from "./sdkProtocolRunner.js";

export function contextUsageControlResponsePayload(context: SdkControlRequestHandlerContext): Promise<Record<string, unknown>> {
  return context.client.getContextUsage({
    sessionId: sdkOptionSessionId(context.options),
    model: context.options.model
  });
}
