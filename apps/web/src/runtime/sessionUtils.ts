import type { ChatMessage, ToolApprovalRequest } from "../types/runtimeTypes";
import { copy } from "../copy";

export const welcome: ChatMessage = {
  id: 1,
  role: "assistant",
  content: copy.chat.welcome
};

export function approvalFromEvent(event: any, fallbackRunId: string): ToolApprovalRequest {
  const call = event.payload?.tool_call || {};
  return {
    approvalId: event.payload?.approval_id || call.id || call.name || event.name || "tool",
    runId: event.payload?.run_id || fallbackRunId,
    toolName: call.name || event.name || "tool",
    arguments: call.arguments || {},
    reason: event.payload?.permission?.reason || copy.approval.reasonFallback,
    impact: event.payload?.impact || {}
  };
}

export function mergeApproval(current: ToolApprovalRequest[], request: ToolApprovalRequest) {
  if (current.some((item) => item.approvalId === request.approvalId)) return current;
  return [...current, request];
}

export function createId() {
  return Date.now() + Math.floor(Math.random() * 1000);
}

export function timeLabel() {
  return new Date().toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function splitCsv(value: string) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

export function compact(payload: Record<string, unknown>) {
  return Object.fromEntries(
    Object.entries(payload).filter(([, value]) => Array.isArray(value) ? value.length > 0 : value !== undefined && value !== null && value !== "")
  );
}

export function safeJson(value: string): any {
  try {
    return JSON.parse(value);
  } catch {
    return { payload: { message: value } };
  }
}

export function errorText(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}
