import type { ModelToolDefinition, ModelTurn } from "../types/modelTypes.js";
import type { Message, ToolCall } from "../types/runtimeTypes.js";
import type { ModelClientConfig } from "./modelClientTypes.js";
import { modelUsageFromClaude } from "./modelUsage.js";
import { objectArguments, recordArray, recordValue, stringValue } from "./modelProtocolValues.js";

export function claudeMessagesRequestBody(
  config: ModelClientConfig,
  messages: Message[],
  tools: ModelToolDefinition[] = []
): Record<string, unknown> {
  const body: Record<string, unknown> = {
    model: config.model,
    max_tokens: config.maxTokens,
    system: messages.filter((message) => message.role === "system").map((message) => message.content).join("\n\n"),
    messages: toClaudeMessages(messages)
  };
  if (tools.length) {
    body.tools = tools.map((tool) => ({
      name: tool.name,
      description: tool.description,
      input_schema: tool.parameters
    }));
  }
  const thinkingBudgetTokens = thinkingBudget(config.maxThinkingTokens, config.maxTokens);
  if (thinkingBudgetTokens !== undefined) {
    body.thinking = {
      type: "enabled",
      budget_tokens: thinkingBudgetTokens
    };
  }
  return body;
}

export function parseClaudeMessagesTurn(payload: unknown): ModelTurn {
  const content = recordArray(recordValue(payload).content);
  return {
    content: content.map(claudeTextBlock).join(""),
    tool_calls: parseClaudeToolCalls(content),
    usage: modelUsageFromClaude(recordValue(payload).usage)
  };
}

export function toClaudeMessages(messages: Message[]): unknown[] {
  const renderedMessages: { role: "user" | "assistant"; content: unknown }[] = [];
  for (const message of messages) {
    if (message.role === "system") continue;
    if (message.role === "tool") {
      appendClaudeToolResult(renderedMessages, {
        type: "tool_result",
        tool_use_id: message.tool_call_id,
        content: message.content
      });
      continue;
    }
    if (message.role === "assistant" && message.tool_calls?.length) {
      const content: unknown[] = [];
      if (message.content) content.push({ type: "text", text: message.content });
      for (const toolCall of message.tool_calls) {
        content.push({
          type: "tool_use",
          id: toolCall.id,
          name: toolCall.name,
          input: toolCall.arguments || {}
        });
      }
      renderedMessages.push({ role: "assistant", content });
      continue;
    }
    renderedMessages.push({
      role: message.role === "assistant" ? "assistant" : "user",
      content: message.content
    });
  }
  return renderedMessages;
}

function appendClaudeToolResult(
  messages: { role: "user" | "assistant"; content: unknown }[],
  block: Record<string, unknown>
): void {
  const previous = messages.at(-1);
  if (
    previous?.role === "user" &&
    Array.isArray(previous.content) &&
    previous.content.every((item) => recordValue(item).type === "tool_result")
  ) {
    previous.content.push(block);
    return;
  }
  messages.push({ role: "user", content: [block] });
}

function parseClaudeToolCalls(content: Record<string, unknown>[]): ToolCall[] {
  return content
    .map((block, index) => {
      if (block.type !== "tool_use") return undefined;
      return {
        id: stringValue(block.id) || `tool_${index}`,
        name: stringValue(block.name),
        arguments: objectArguments(block.input)
      };
    })
    .filter((toolCall): toolCall is ToolCall => Boolean(toolCall?.name));
}

function claudeTextBlock(block: Record<string, unknown>): string {
  return block.type === "text" ? stringValue(block.text) : "";
}

function thinkingBudget(value: unknown, maxTokens: number): number | undefined {
  const budget = Number(value);
  if (value === undefined || value === null || value === "") return undefined;
  if (!Number.isInteger(budget) || budget <= 0) return undefined;
  if (budget >= maxTokens) throw new Error("maxThinkingTokens must be less than maxTokens for Claude Messages");
  return budget;
}
