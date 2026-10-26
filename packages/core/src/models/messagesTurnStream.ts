import type { ModelClientConfig } from "./modelClientTypes.js";
import { ModelProtocolError } from "./modelErrors.js";
import { parseClaudeMessagesTurn } from "./anthropicProtocolPayloads.js";
import { parseProtocolJson, requireRecord, requireString } from "./modelProtocolValidation.js";
import { streamIndex, streamRecord, streamString, type TurnStreamDecoder } from "./modelTurnStreamState.js";

type BlockState = { block: Record<string, unknown>; text: string[]; signature: string[]; arguments: string[] };

export function messagesTurnStream(config: ModelClientConfig): TurnStreamDecoder {
  const content: Record<string, unknown>[] = [];
  let active: BlockState | undefined;
  let started = false;
  let reason: string | undefined;
  let usage: Record<string, unknown> = {};
  return event => {
    const record = streamRecord(event);
    switch (record.type) {
      case "ping": return { events: [] };
      case "message_start": {
        if (started) throw new ModelProtocolError("duplicate Messages start");
        const message = requireRecord(record.message, "message start");
        if (!Array.isArray(message.content) || message.content.length) throw new ModelProtocolError("Messages stream must start with empty content");
        usage = requireRecord(message.usage, "message usage");
        started = true;
        return { events: [] };
      }
      case "content_block_start": {
        const index = streamIndex(record.index);
        if (!started || reason || active || index !== content.length) throw new ModelProtocolError("invalid Messages block start");
        const block = requireRecord(record.content_block, "content block");
        active = { block: { ...block }, text: [], signature: [], arguments: [] };
        switch (block.type) {
          case "text": {
            const delta = streamString(block.text);
            active.text.push(delta);
            return { events: delta ? [{ type: "text_delta", delta }] : [] };
          }
          case "tool_use":
            if (Object.keys(requireRecord(block.input, "initial tool input")).length) throw new ModelProtocolError("streamed tool input must start empty");
            return { events: [{ type: "tool_call_delta", index, id: requireString(block.id, "tool id"), name: requireString(block.name, "tool name") }] };
          case "thinking": active.text.push(streamString(block.thinking)); return { events: [] };
          case "redacted_thinking": requireString(block.data, "redacted thinking data"); return { events: [] };
          default: throw new ModelProtocolError("unsupported Messages block type");
        }
      }
      case "content_block_delta": {
        if (!active || record.index !== content.length) throw new ModelProtocolError("Messages delta has no matching block");
        const delta = requireRecord(record.delta, "block delta");
        if (active.block.type === "tool_use" && delta.type === "input_json_delta") {
          const part = streamString(delta.partial_json);
          active.arguments.push(part);
          return { events: [{ type: "tool_call_delta", index: content.length, argumentsDelta: part }] };
        }
        if (active.block.type === "text" && delta.type === "text_delta") {
          const part = streamString(delta.text);
          active.text.push(part);
          return { events: [{ type: "text_delta", delta: part }] };
        }
        if (active.block.type === "thinking" && delta.type === "thinking_delta") { active.text.push(streamString(delta.thinking)); return { events: [] }; }
        if (active.block.type === "thinking" && delta.type === "signature_delta") { active.signature.push(streamString(delta.signature)); return { events: [] }; }
        throw new ModelProtocolError("unexpected Messages block delta");
      }
      case "content_block_stop": {
        if (!active || record.index !== content.length) throw new ModelProtocolError("Messages stop has no matching block");
        const { block, text, signature, arguments: parts } = active;
        if (block.type === "text") block.text = text.join("");
        if (block.type === "thinking") {
          block.thinking = text.join("");
          block.signature = requireString(signature.join(""), "thinking signature");
        }
        if (block.type === "tool_use") block.input = parts.length ? requireRecord(parseProtocolJson(parts.join("")), "tool input") : {};
        content.push(block);
        active = undefined;
        return { events: [] };
      }
      case "message_delta":
        if (!started || reason || active) throw new ModelProtocolError("invalid Messages finish");
        reason = requireString(requireRecord(record.delta, "message delta").stop_reason, "stop reason");
        if (!["end_turn", "stop_sequence", "tool_use"].includes(reason)) throw new ModelProtocolError("Messages stream did not complete normally");
        usage = { ...usage, ...requireRecord(record.usage, "message delta usage") };
        return { events: [] };
      case "message_stop": {
        if (!reason) throw new ModelProtocolError("Messages stream is missing a stop reason");
        const hasTools = content.some(block => block.type === "tool_use");
        if (hasTools !== (reason === "tool_use")) throw new ModelProtocolError("Messages tools do not match stop reason");
        return { events: [], turn: parseClaudeMessagesTurn({ content, usage, stop_reason: reason }, config) };
      }
      default: throw new ModelProtocolError("unsupported Messages stream event");
    }
  };
}
