import type { ModelToolDefinition, ModelTurn } from "../types/modelTypes.js";
import type { Message, ToolCall } from "../types/runtimeTypes.js";
import type { ModelClientConfig } from "./modelClientTypes.js";
import { ModelProtocolError } from "./modelErrors.js";
import { parseFunctionCall, requireArray, requireRecord, validateCallIds } from "./modelProtocolValidation.js";
import { modelUsageFromOpenAIChat, modelUsageFromOpenAIResponses } from "./modelUsage.js";
import { recordArray, recordValue, stringValue } from "./modelProtocolValues.js";

export function openAIChatRequestBody(
  config: ModelClientConfig,
  messages: Message[],
  tools: ModelToolDefinition[] = []
): Record<string, unknown> {
  const body: Record<string, unknown> = {
    model: config.model,
    messages: toOpenAIChatMessages(messages),
    max_tokens: config.maxTokens
  };
  if (tools.length) body.tools = tools.map((tool) => ({ type: "function", function: tool }));
  return body;
}

export function parseOpenAIChatTurn(payload: unknown): ModelTurn {
  const root = requireRecord(payload, "Chat response");
  const choices = requireArray(root.choices, "Chat choices");
  const choice = requireRecord(choices[0], "Chat first choice");
  if (choice.finish_reason === "length" || choice.finish_reason === "content_filter") {
    throw new ModelProtocolError("Chat response did not complete normally");
  }
  const message = requireRecord(choice.message, "Chat message");
  if (message.content === undefined && message.refusal === undefined && message.tool_calls === undefined) {
    throw new ModelProtocolError("Chat message has no content or tool calls");
  }
  if (message.content != null && typeof message.content !== "string") {
    throw new ModelProtocolError("Chat message content must be text or null");
  }
  return {
    content: stringValue(message.content ?? message.refusal),
    tool_calls: parseOpenAIToolCalls(message.tool_calls),
    usage: modelUsageFromOpenAIChat(recordValue(payload).usage)
  };
}

export function responsesRequestBody(
  config: ModelClientConfig,
  messages: Message[],
  tools: ModelToolDefinition[] = []
): Record<string, unknown> {
  const body: Record<string, unknown> = {
    model: config.model,
    input: toResponsesInput(messages),
    max_output_tokens: config.maxTokens
  };
  if (tools.length) {
    body.tools = tools.map((tool) => ({
      type: "function",
      name: tool.name,
      description: tool.description,
      parameters: tool.parameters
    }));
  }
  return body;
}

export function parseResponsesTurn(payload: unknown): ModelTurn {
  const root = requireRecord(payload, "Responses response");
  if (root.error || (root.status !== undefined && root.status !== "completed")) {
    throw new ModelProtocolError("Responses response did not complete normally");
  }
  requireArray(root.output, "Responses output");
  return {
    content: responseOutputText(payload),
    tool_calls: parseResponsesToolCalls(recordValue(payload).output),
    usage: modelUsageFromOpenAIResponses(recordValue(payload).usage)
  };
}

export function toOpenAIChatMessages(messages: Message[]): unknown[] {
  return messages.map((message) => {
    if (message.role === "tool") return { role: "tool", tool_call_id: message.tool_call_id, content: message.content };
    if (message.tool_calls?.length) {
      return {
        role: message.role,
        content: message.content || null,
        tool_calls: message.tool_calls.map((toolCall) => ({
          id: toolCall.id,
          type: "function",
          function: {
            name: toolCall.name,
            arguments: JSON.stringify(toolCall.arguments || {})
          }
        }))
      };
    }
    return { role: message.role, content: message.content };
  });
}

export function toResponsesInput(messages: Message[]): unknown[] {
  const input: unknown[] = [];
  for (const message of messages) {
    if (message.role === "tool") {
      input.push({
        type: "function_call_output",
        call_id: message.tool_call_id,
        output: message.content
      });
      continue;
    }
    if (message.tool_calls?.length) {
      if (message.content) input.push({ role: "assistant", content: message.content });
      for (const toolCall of message.tool_calls) {
        input.push({
          type: "function_call",
          call_id: toolCall.id,
          name: toolCall.name,
          arguments: JSON.stringify(toolCall.arguments || {})
        });
      }
      continue;
    }
    input.push({ role: message.role, content: message.content });
  }
  return input;
}

function parseOpenAIToolCalls(value: unknown): ToolCall[] {
  if (value === undefined) return [];
  return validateCallIds(requireArray(value, "Chat tool calls").map(item => {
    const call = requireRecord(item, "Chat tool call");
    if (call.type !== undefined && call.type !== "function") throw new ModelProtocolError("unsupported Chat tool call type");
    const fn = requireRecord(call.function, "Chat tool function");
    return parseFunctionCall(call.id, fn.name, fn.arguments, "json");
  }));
}

function parseResponsesToolCalls(value: unknown): ToolCall[] {
  const calls: ToolCall[] = [];
  for (const item of requireArray(value, "Responses output")) {
    const call = requireRecord(item, "Responses output item");
    if (call.type !== "function_call") continue;
    if (call.status !== undefined && call.status !== "completed") throw new ModelProtocolError("incomplete Responses function call");
    calls.push(parseFunctionCall(call.call_id, call.name, call.arguments, "json"));
  }
  return validateCallIds(calls);
}

function responseOutputText(payload: unknown): string {
  const payloadRecord = recordValue(payload);
  if (typeof payloadRecord.output_text === "string") return payloadRecord.output_text;
  return recordArray(payloadRecord.output).map(responseOutputItemText).join("");
}

function responseOutputItemText(item: unknown): string {
  const itemRecord = recordValue(item);
  if (typeof itemRecord.text === "string") return itemRecord.text;
  return recordArray(itemRecord.content).map((block) => stringValue(block.text)).join("");
}
