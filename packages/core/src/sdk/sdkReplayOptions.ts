import type { SdkQueryOptions } from "./sdkQueryOptions.js";

export function sdkReplayUserMessagesOption(options: Pick<SdkQueryOptions, "replayUserMessages" | "replay_user_messages" | "metadata">): boolean | undefined {
  return booleanOption(
    options.replayUserMessages
      ?? options.replay_user_messages
      ?? options.metadata?.replayUserMessages
      ?? options.metadata?.replay_user_messages
  );
}

function booleanOption(value: unknown): boolean | undefined {
  if (typeof value === "boolean") return value;
  if (typeof value !== "string") return undefined;
  const normalized = value.trim().toLowerCase();
  if (["1", "true", "yes", "on"].includes(normalized)) return true;
  if (["0", "false", "no", "off"].includes(normalized)) return false;
  return undefined;
}
