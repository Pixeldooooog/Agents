import type { ModelToolDefinition, ModelTurn } from "../types/modelTypes.js";
import type { Message, ToolCall } from "../types/runtimeTypes.js";
import type { ModelClientConfig } from "./modelClientTypes.js";
import { parseModelJson } from "./modelHttp.js";
import { modelUsageFromOpenAIChat, modelUsageFromOpenAIResponses } from "./modelUsage.js";
import { objectArguments, recordArray, recordValue, stringValue } from "./modelProtocolValues.js";

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
  const choice = recordArray(recordValue(payload).choices)[0] || {};
  const message = recordValue(choice.message);
  return {
    content: stringValue(message.content),
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
  return recordArray(value)
    .map((payload, index) => {
      const fn = recordValue(payload.function);
      return {
        id: stringValue(payload.id) || `tool_${index}`,
        name: stringValue(fn.name) || stringValue(payload.name),
        arguments: parseToolArguments(fn.arguments || payload.arguments)
      };
    })
    .filter((toolCall) => toolCall.name);
}

function parseResponsesToolCalls(value: unknown): ToolCall[] {
  return recordArray(value)
    .map((payload, index) => {
      if (payload.type !== "function_call") return undefined;
      return {
        id: stringValue(payload.call_id) || stringValue(payload.id) || `tool_${index}`,
        name: stringValue(payload.name),
        arguments: parseToolArguments(payload.arguments)
      };
    })
    .filter((toolCall): toolCall is ToolCall => Boolean(toolCall?.name));
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

function parseToolArguments(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) return objectArguments(value);
  return objectArguments(parseModelJson(stringValue(value) || "{}"));
}
