import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { todoSummary } from "../planning/planningState.js";
import type { JsonObject } from "../types/jsonTypes.js";
import type { ToolContext } from "../tools/toolContracts.js";

type SessionReadContext = ToolContext<never, "conversation">;
type SessionEditContext = ToolContext<"conversation">;
import { relativeWorkspacePath } from "../tools/toolInputs.js";
import { exportFormat, exportPath, jsonExport, markdownExport } from "./sessionContextExports.js";
import { filteredMessages, loadPlanningState, roleCounts, workspacePayload } from "./sessionContextPayloads.js";
import { boundedNumber, conversationSummary, estimateTokens, truncate } from "./sessionContextText.js";

export async function handleSessionStatus(context: ToolContext<never, "conversation" | "store">): Promise<Record<string, unknown>> {
  const messages = context.conversation?.messages || [];
  const planning = await loadPlanningState(context);
  return {
    workspace: workspacePayload(context),
    model: {
      protocol: context.spec?.protocol || "",
      model: context.spec?.model || ""
    },
    tools: context.spec?.enabled_tools || [],
    messages: {
      total: messages.length,
      non_system: messages.filter((message) => message.role !== "system").length,
      estimated_tokens: estimateTokens(messages),
      max_context_tokens: 0
    },
    context_trace: context.conversation?.runtimeEvents.length || 0,
    todos: todoSummary(planning?.todos || []),
    plan_mode: Boolean(planning?.plan_mode)
  };
}

export async function handleSessionExport(context: SessionReadContext, args: JsonObject): Promise<Record<string, unknown>> {
  const format = exportFormat(args.format);
  const targetPath = exportPath(context.repoRoot, String(args.path || ""), format);
  const messages = filteredMessages(context.conversation?.messages || [], Boolean(args.include_system));
  const content = format === "json" ? jsonExport(context, messages) : markdownExport(context, messages);
  await mkdir(path.dirname(targetPath), { recursive: true });
  await writeFile(targetPath, content);
  return {
    path: relativeWorkspacePath(context.repoRoot, targetPath),
    bytes: Buffer.byteLength(content),
    format,
    messages: messages.length
  };
}

export async function handleSessionSummary(context: SessionReadContext, args: JsonObject): Promise<Record<string, unknown>> {
  const messages = filteredMessages(context.conversation?.messages || [], Boolean(args.include_system));
  const limit = boundedNumber(args.max_messages, 50, 1, 200);
  const maxChars = boundedNumber(args.max_chars, 2000, 80, 20000);
  const selectedMessages = messages.slice(-limit);
  const summary = truncate(conversationSummary(selectedMessages), maxChars);
  return {
    summary,
    messages: selectedMessages.length,
    total: messages.length,
    roles: roleCounts(selectedMessages),
    truncated: summary.length >= maxChars
  };
}

export async function handleContextTrace(context: SessionReadContext, args: JsonObject): Promise<Record<string, unknown>> {
  const maxChars = boundedNumber(args.max_chars, 240, 0, 20000);
  const includeText = Boolean(args.include_text);
  const items = (context.conversation?.runtimeEvents || []).map((event, index) => {
    const eventText = JSON.stringify(event);
    const previewText = JSON.stringify(event.payload || event.raw || event.type);
    return {
      id: `${index}`,
      layer: "runtime",
      source: event.name || event.type,
      priority: 0,
      included: true,
      tokens: estimateTokens([{ content: eventText }]),
      ...(includeText ? { text: truncate(eventText, maxChars) } : { preview: truncate(previewText, maxChars) })
    };
  });
  return { items, count: items.length };
}

export async function handleContextMessages(context: SessionReadContext, args: JsonObject): Promise<Record<string, unknown>> {
  const messages = filteredMessages(context.conversation?.messages || [], Boolean(args.include_system));
  const limit = boundedNumber(args.max_messages, 50, 1, 200);
  const maxChars = boundedNumber(args.max_chars, 240, 0, 20000);
  const selectedMessages = messages.slice(-limit);
  return {
    messages: selectedMessages.map((message, index) => ({
      index: Math.max(0, messages.length - selectedMessages.length) + index,
      role: message.role,
      content: truncate(message.content, maxChars),
      tool_calls: (message.tool_calls || []).map((toolCall) => toolCall.name)
    })),
    count: selectedMessages.length,
    total: messages.length
  };
}

export async function handleContextCompact(context: SessionEditContext, args: JsonObject): Promise<Record<string, unknown>> {
  const { messages } = context.conversation;
  const beforeMessages = messages.length;
  const nonSystem = messages.filter((message) => message.role !== "system");
  if (nonSystem.length <= 4) return { before_messages: beforeMessages, after_messages: messages.length, compacted: false };
  const maxSummaryChars = Math.max(240, Number(args.target_tokens || 0) * 4 || 2000);
  const summary = truncate(conversationSummary(nonSystem.slice(0, -2)), maxSummaryChars);
  const systemMessages = messages.filter((message) => message.role === "system");
  const tailMessages = nonSystem.slice(-2);
  messages.splice(
    0,
    messages.length,
    ...systemMessages,
    { role: "assistant", content: `Context summary:\n${summary}` },
    ...tailMessages
  );
  return { before_messages: beforeMessages, after_messages: messages.length, compacted: true };
}

export async function handleContextRewind(context: SessionEditContext, args: JsonObject): Promise<Record<string, unknown>> {
  const { messages } = context.conversation;
  const dropCount = boundedNumber(args.drop_last, 1, 1, 200);
  const beforeMessages = messages.length;
  let droppedMessages = 0;
  for (let index = messages.length - 1; index >= 0 && droppedMessages < dropCount; index -= 1) {
    if (messages[index].role !== "system") {
      messages.splice(index, 1);
      droppedMessages += 1;
    }
  }
  return { before_messages: beforeMessages, after_messages: messages.length, dropped_messages: droppedMessages };
}
