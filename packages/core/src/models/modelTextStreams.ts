import { ModelProtocolError } from "./modelErrors.js";
import { parseProtocolJson, requireArray, requireRecord } from "./modelProtocolValidation.js";
import type { TextStreamStep } from "./modelClientTypes.js";
import type { SseEvent } from "./modelSse.js";

function payload(event: SseEvent): Record<string, unknown> {
  const record = requireRecord(parseProtocolJson(event.data), "stream payload");
  if (event.event === "error" || record.error || record.type === "error") {
    throw new ModelProtocolError("model stream returned an error");
  }
  return record;
}

function textDelta(value: unknown): string {
  if (typeof value !== "string") throw new ModelProtocolError("stream text delta must be a string");
  return value;
}

/** Each request owns its protocol state. Text APIs reject unexpected tool output. */
export function chatTextStream(): (event: SseEvent) => TextStreamStep {
  let finished = false;
  return event => {
    if (event.data === "[DONE]") {
      if (!finished) throw new ModelProtocolError("Chat stream is missing a successful finish reason");
      return { done: true };
    }
    const record = payload(event);
    const choices = requireArray(record.choices, "stream choices");
    if (!choices.length) return {}; // Optional usage-only chunk.
    if (choices.length !== 1) throw new ModelProtocolError("text stream expects one choice");
    const choice = requireRecord(choices[0], "stream choice");
    if (choice.index !== 0) throw new ModelProtocolError("unexpected Chat choice index");
    if (finished) throw new ModelProtocolError("Chat choice arrived after finish");
    const delta = requireRecord(choice.delta, "Chat delta");
    if (delta.tool_calls || delta.function_call) throw new ModelProtocolError("text stream received tool calls");
    if (choice.finish_reason != null) {
      if (choice.finish_reason !== "stop") throw new ModelProtocolError("Chat stream did not finish normally");
      finished = true;
    }
    return { delta: delta.content == null ? undefined : textDelta(delta.content) };
  };
}

export function responsesTextStream(event: SseEvent): TextStreamStep {
  const record = payload(event);
  if (record.type === "response.failed" || record.type === "response.incomplete") {
    throw new ModelProtocolError("Responses stream did not complete normally");
  }
  if (record.type === "response.completed") {
    const response = requireRecord(record.response, "completed response");
    if (response.status !== "completed") throw new ModelProtocolError("invalid Responses completion status");
    const output = requireArray(response.output, "completed output");
    if (output.some(item => requireRecord(item, "output item").type === "function_call")) {
      throw new ModelProtocolError("text stream received tool calls");
    }
    return { done: true };
  }
  if (record.type === "response.output_item.added" && requireRecord(record.item, "output item").type === "function_call") {
    throw new ModelProtocolError("text stream received tool calls");
  }
  return record.type === "response.output_text.delta" ? { delta: textDelta(record.delta) } : {};
}

export function messagesTextStream(): (event: SseEvent) => TextStreamStep {
  let started = false;
  let finished = false;
  let activeIndex: number | undefined;
  let nextIndex = 0;
  let blockType: unknown;
  return event => {
    const record = payload(event);
    switch (record.type) {
      case "ping": return {};
      case "message_start":
        if (started) throw new ModelProtocolError("duplicate Messages start");
        requireRecord(record.message, "message");
        started = true;
        return {};
      case "content_block_start": {
        if (!started || finished || activeIndex !== undefined || record.index !== nextIndex) {
          throw new ModelProtocolError("invalid Messages block start");
        }
        const block = requireRecord(record.content_block, "content block");
        blockType = block.type;
        if (blockType !== "text" && blockType !== "thinking" && blockType !== "redacted_thinking") {
          throw new ModelProtocolError("unsupported text stream content block");
        }
        activeIndex = nextIndex++;
        return blockType === "text" ? { delta: textDelta(block.text) } : {};
      }
      case "content_block_delta": {
        if (activeIndex === undefined || record.index !== activeIndex) throw new ModelProtocolError("Messages delta has no matching block");
        const delta = requireRecord(record.delta, "content delta");
        if (delta.type === "text_delta" && blockType === "text") return { delta: textDelta(delta.text) };
        if (blockType === "thinking" && (delta.type === "thinking_delta" || delta.type === "signature_delta")) return {};
        throw new ModelProtocolError("unexpected Messages content delta");
      }
      case "content_block_stop":
        if (activeIndex === undefined || record.index !== activeIndex) throw new ModelProtocolError("Messages stop has no matching block");
        activeIndex = undefined;
        return {};
      case "message_delta": {
        if (!started || finished || activeIndex !== undefined) throw new ModelProtocolError("invalid Messages finish");
        const reason = requireRecord(record.delta, "message delta").stop_reason;
        if (reason !== "end_turn" && reason !== "stop_sequence") throw new ModelProtocolError("Messages stream did not finish normally");
        finished = true;
        return {};
      }
      case "message_stop":
        if (!finished) throw new ModelProtocolError("Messages stream is missing a successful stop reason");
        return { done: true };
      default: throw new ModelProtocolError("unsupported Messages stream event");
    }
  };
}
