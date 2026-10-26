import { isDeepStrictEqual } from "node:util";
import type { ModelClientConfig } from "./modelClientTypes.js";
import { ModelProtocolError } from "./modelErrors.js";
import { requireArray, requireRecord, requireString } from "./modelProtocolValidation.js";
import { parseResponsesTurn } from "./openaiProtocolPayloads.js";
import { immutableField, streamIndex, streamRecord, streamString, type TurnStreamDecoder } from "./modelTurnStreamState.js";

type OutputState = { item: Record<string, unknown>; arguments: string[]; text: Map<number, string[]>; done?: Record<string, unknown> };

export function responsesTurnStream(config: ModelClientConfig): TurnStreamDecoder {
  const items = new Map<number, OutputState>();
  const itemIds = new Set<string>();
  let responseId: string | undefined;
  return event => {
    const record = streamRecord(event);
    const type = requireString(record.type, "Responses event type");
    if (type === "response.failed" || type === "response.incomplete") throw new ModelProtocolError("Responses stream did not complete normally");
    if (type === "response.created" || type === "response.in_progress") {
      responseId = immutableField(responseId, requireRecord(record.response, "response").id);
    }
    if (type === "response.completed") {
      const response = requireRecord(record.response, "completed response");
      responseId = immutableField(responseId, response.id);
      if (response.status !== "completed") throw new ModelProtocolError("invalid Responses terminal status");
      const output = requireArray(response.output, "response output");
      if (output.length !== items.size) throw new ModelProtocolError("Responses output does not match streamed items");
      output.forEach((value, index) => {
        if (!items.get(index)?.done || !isDeepStrictEqual(items.get(index)?.done, value)) {
          throw new ModelProtocolError("Responses final item differs from streamed item");
        }
      });
      return { events: [], turn: parseResponsesTurn(response, config) };
    }
    if (type === "response.output_item.added") {
      const index = streamIndex(record.output_index);
      if (items.has(index)) throw new ModelProtocolError("duplicate Responses output index");
      const item = requireRecord(record.item, "output item");
      const itemId = requireString(item.id, "output item id");
      if (itemIds.has(itemId)) throw new ModelProtocolError("duplicate Responses output item id");
      itemIds.add(itemId);
      if (item.type !== "message" && item.type !== "reasoning" && item.type !== "function_call") {
        throw new ModelProtocolError("unsupported Responses output item");
      }
      items.set(index, { item, arguments: [], text: new Map() });
      if (item.type === "function_call") {
        if (item.arguments !== "") throw new ModelProtocolError("function call must start with empty arguments");
        return { events: [{ type: "tool_call_delta", index, id: requireString(item.call_id, "call id"), name: requireString(item.name, "function name") }] };
      }
      return { events: [] };
    }
    if (type === "response.output_item.done") {
      const index = streamIndex(record.output_index);
      const state = items.get(index);
      const item = requireRecord(record.item, "completed output item");
      if (!state || state.done || state.item.id !== item.id || state.item.type !== item.type) throw new ModelProtocolError("invalid Responses item completion");
      if (item.type === "function_call" && (item.call_id !== state.item.call_id || item.name !== state.item.name || item.arguments !== state.arguments.join(""))) {
        throw new ModelProtocolError("Responses tool arguments or identity changed");
      }
      if (item.type === "message") {
        const content = requireArray(item.content, "message content");
        for (const [contentIndex, parts] of state.text) {
          const block = requireRecord(content[contentIndex], "message content block");
          if ((block.text ?? block.refusal) !== parts.join("")) throw new ModelProtocolError("Responses final text differs from deltas");
        }
      }
      state.done = item;
      return { events: [] };
    }
    if (type === "response.function_call_arguments.delta" || type === "response.output_text.delta" || type === "response.refusal.delta") {
      const index = streamIndex(record.output_index);
      const state = items.get(index);
      if (!state || state.done || record.item_id !== state.item.id) throw new ModelProtocolError("Responses delta has no matching item");
      const delta = streamString(record.delta);
      if (type === "response.function_call_arguments.delta") {
        if (state.item.type !== "function_call") throw new ModelProtocolError("arguments delta targets non-tool item");
        state.arguments.push(delta);
        return { events: [{ type: "tool_call_delta", index, argumentsDelta: delta }] };
      }
      if (state.item.type !== "message") throw new ModelProtocolError("text delta targets non-message item");
      const contentIndex = streamIndex(record.content_index);
      const parts = state.text.get(contentIndex) ?? [];
      parts.push(delta);
      state.text.set(contentIndex, parts);
      return { events: [{ type: "text_delta", delta }] };
    }
    // Metadata, content-part and reasoning events are retained in the authoritative output item.
    return { events: [] };
  };
}
