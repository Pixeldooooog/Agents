import type { Message } from "../types/runtimeTypes.js";

/** Keep an assistant's calls and subsequent results together, including the currently executing group. */
export function conversationGroups(messages: readonly Message[]): Message[][] {
  const groups: Message[][] = [];
  for (const message of messages) {
    if (message.role === "system") continue;
    const previous = groups.at(-1);
    if (message.role === "tool" && previous?.[0].role === "assistant" && previous[0].tool_calls?.some(call => call.id === message.tool_call_id)) previous.push(message);
    else groups.push([message]);
  }
  return groups;
}

export function hasPendingResults(group: readonly Message[]): boolean {
  const results = new Set(group.filter(message => message.role === "tool").map(message => message.tool_call_id));
  return !!group[0]?.tool_calls?.some(call => !results.has(call.id));
}
