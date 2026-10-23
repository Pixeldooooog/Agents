import type {
  ActivityEvent,
  ActivityEventKind,
  ActivityEventStatus,
  ChatMessage,
  OperationEvent,
  Role
} from "../types/runtimeTypes";
import { timeLabel } from "./sessionUtils";

export function createChatMessage(id: number, role: Role, content: string): ChatMessage {
  return { id, role, content };
}

export function updateChatMessageContent(messages: ChatMessage[], id: number, content: string, append = false): ChatMessage[] {
  return messages.map((message) => message.id === id ? { ...message, content: append ? `${message.content}${content}` : content } : message);
}

export function removeChatMessage(messages: ChatMessage[], id: number): ChatMessage[] {
  return messages.filter((message) => message.id !== id);
}

export function createActivityRecord(id: number, kind: ActivityEventKind, title: string, detail: string, status: ActivityEventStatus): ActivityEvent {
  return { id, kind, title, detail, status, time: timeLabel() };
}

export function updateActivityRecord(events: ActivityEvent[], id: number, patch: Partial<ActivityEvent>): ActivityEvent[] {
  return events.map((event) => event.id === id ? { ...event, ...patch } : event);
}

export function appendUniqueOperationEvents(current: OperationEvent[], nextEvents: OperationEvent[], maxEvents: number): OperationEvent[] {
  const seenIds = new Set(current.map((event) => event.id));
  return [...current, ...nextEvents.filter((event) => !seenIds.has(event.id))].slice(-maxEvents);
}
