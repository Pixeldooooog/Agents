import type { SdkUserMessage } from "./sdkMessages.js";
import { newSdkUserMessageUuid } from "./sdkUserMessageIds.js";

export type SdkAsyncMessagePriority = "now" | "next" | "later";

export type SdkAsyncMessageInput = SdkUserMessage | Partial<SdkUserMessage> | Record<string, unknown> | string;

export type SdkAsyncMessageOptions = {
  sessionId?: string;
  session_id?: string;
  priority?: SdkAsyncMessagePriority;
};

type SdkAsyncMessageQueueItem = {
  sequence: number;
  message: SdkUserMessage;
};

export class SdkAsyncMessageQueue {
  private nextSequence = 0;
  private readonly items: SdkAsyncMessageQueueItem[] = [];

  enqueue(message: SdkAsyncMessageInput, options: SdkAsyncMessageOptions = {}): SdkUserMessage {
    const queuedMessage = sdkAsyncUserMessage(message, options);
    this.items.push({ sequence: this.nextSequence, message: queuedMessage });
    this.nextSequence += 1;
    return queuedMessage;
  }

  list(sessionId = ""): SdkUserMessage[] {
    return this.sortedItems(sessionId).map((item) => ({ ...item.message }));
  }

  dequeue(sessionId = ""): SdkUserMessage | undefined {
    const target = this.sortedItems(sessionId)[0];
    if (!target) return undefined;
    const index = this.items.indexOf(target);
    if (index >= 0) this.items.splice(index, 1);
    return { ...target.message };
  }

  cancel(messageUuid: string): SdkUserMessage[] {
    const resolvedUuid = messageUuid.trim();
    if (!resolvedUuid) throw new Error("messageUuid is required");
    const removed: SdkAsyncMessageQueueItem[] = [];
    for (let index = this.items.length - 1; index >= 0; index -= 1) {
      const item = this.items[index];
      if (item.message.uuid !== resolvedUuid) continue;
      removed.push(...this.items.splice(index, 1));
    }
    return sortAsyncMessageItems(removed).map((item) => ({ ...item.message }));
  }

  has(options: { sessionId?: string; maxPriority?: SdkAsyncMessagePriority } = {}): boolean {
    const resolvedSessionId = String(options.sessionId || "").trim();
    const maxRank = asyncMessagePriorityRank(options.maxPriority || "later");
    return this.items.some((item) => {
      if (resolvedSessionId && item.message.sessionId !== resolvedSessionId) return false;
      return asyncMessagePriorityRank(item.message.priority) <= maxRank;
    });
  }

  private sortedItems(sessionId: string): SdkAsyncMessageQueueItem[] {
    const resolvedSessionId = sessionId.trim();
    return sortAsyncMessageItems(
      this.items.filter((item) => !resolvedSessionId || item.message.sessionId === resolvedSessionId)
    );
  }
}

export function sdkAsyncUserMessage(message: SdkAsyncMessageInput, options: SdkAsyncMessageOptions): SdkUserMessage {
  const priority = asyncMessagePriorityOption(options.priority);
  if (typeof message === "string") {
    return {
      type: "user_message",
      uuid: newSdkUserMessageUuid(),
      sessionId: String(options.sessionId || options.session_id || ""),
      content: message,
      priority: priority || "next",
      isReplay: false
    };
  }

  const record = objectRecord(message);
  const nestedMessage = objectRecord(record.message);
  const sessionId = String(options.sessionId || options.session_id || record.sessionId || record.session_id || "");
  const content = stringField(record.content) || messageContentText(nestedMessage);
  return {
    type: "user_message",
    uuid: stringField(record.uuid) || newSdkUserMessageUuid(),
    sessionId,
    content,
    ...(nestedMessage ? { message: nestedMessage } : {}),
    ...optionalStringProperty("parentToolUseId", record.parentToolUseId ?? record.parent_tool_use_id),
    ...optionalBooleanProperty("isSynthetic", record.isSynthetic ?? record.is_synthetic),
    ...(record.toolUseResult !== undefined || record.tool_use_result !== undefined
      ? { toolUseResult: record.toolUseResult ?? record.tool_use_result }
      : {}),
    priority: priority || asyncMessagePriorityRecord(record.priority) || "next",
    ...optionalStringProperty("timestamp", record.timestamp),
    isReplay: booleanField(record.isReplay ?? record.is_replay) ?? false
  };
}

function sortAsyncMessageItems(items: SdkAsyncMessageQueueItem[]): SdkAsyncMessageQueueItem[] {
  return [...items].sort((left, right) => {
    const priorityDelta = asyncMessagePriorityRank(left.message.priority) - asyncMessagePriorityRank(right.message.priority);
    return priorityDelta || left.sequence - right.sequence;
  });
}

function asyncMessagePriority(value: unknown): SdkAsyncMessagePriority | undefined {
  return value === "now" || value === "next" || value === "later" ? value : undefined;
}

function asyncMessagePriorityOption(value: unknown): SdkAsyncMessagePriority | undefined {
  if (value === undefined || value === null) return undefined;
  const priority = asyncMessagePriority(value);
  if (!priority) throw new Error("async message priority must be now, next, or later");
  return priority;
}

function asyncMessagePriorityRecord(value: unknown): SdkAsyncMessagePriority | undefined {
  if (value === undefined || value === null || value === "") return undefined;
  const priority = asyncMessagePriority(value);
  if (!priority) throw new Error("async message priority must be now, next, or later");
  return priority;
}

function asyncMessagePriorityRank(value: unknown): number {
  if (value === "now") return 0;
  if (value === "later") return 2;
  return 1;
}

function objectRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function stringField(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function booleanField(value: unknown): boolean | undefined {
  return typeof value === "boolean" ? value : undefined;
}

function optionalStringProperty(key: string, value: unknown): Record<string, string> {
  const text = stringField(value);
  return text ? { [key]: text } : {};
}

function optionalBooleanProperty(key: string, value: unknown): Record<string, boolean> {
  const bool = booleanField(value);
  return bool === undefined ? {} : { [key]: bool };
}

function messageContentText(message: Record<string, unknown>): string {
  const content = message.content;
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content.map((item) => {
    const block = objectRecord(item);
    return block.type === "text" ? String(block.text || "") : "";
  }).join("");
}
