import type { Message } from "../types/runtimeTypes.js";

export function conversationSummary(messages: Message[]): string {
  if (!messages.length) return "No conversation messages yet.";
  return [
    "Session summary:",
    ...messages.map((message) => {
      const text = message.content.trim() || toolCallSummary(message);
      return `- ${message.role}: ${text.slice(0, 240)}`;
    })
  ].join("\n");
}

export function estimateTokens(messages: { content: string }[]): number {
  return Math.ceil(messages.reduce((total, message) => total + message.content.length, 0) / 4);
}

export function boundedNumber(value: unknown, fallback: number, minimum: number, maximum: number): number {
  const numericValue = Number(value || fallback);
  if (!Number.isFinite(numericValue)) return fallback;
  return Math.max(minimum, Math.min(maximum, numericValue));
}

export function truncate(value: string, maxChars: number): string {
  if (maxChars <= 0 || value.length <= maxChars) return value;
  return `${value.slice(0, maxChars)}\n[truncated]`;
}

function toolCallSummary(message: Message): string {
  if (!message.tool_calls?.length) return "(empty)";
  return `tool calls: ${message.tool_calls.map((toolCall) => toolCall.name).join(", ")}`;
}
