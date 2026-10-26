import type { ModelStreamEvent } from "../types/modelTypes.js";
import { ModelProtocolError } from "./modelErrors.js";
import { requireArray, requireRecord } from "./modelProtocolValidation.js";
import { parseOpenAIChatTurn } from "./openaiProtocolPayloads.js";
import { immutableField, streamIndex, streamRecord, streamString, type TurnStreamDecoder } from "./modelTurnStreamState.js";

type CallParts = { id?: string; name?: string; parts: string[] };

export function chatTurnStream(): TurnStreamDecoder {
  const text: string[] = [];
  const calls = new Map<number, CallParts>();
  let finish: string | undefined;
  let usage: unknown;
  return event => {
    if (event.data === "[DONE]") {
      if (!finish || (finish === "tool_calls") !== Boolean(calls.size)) throw new ModelProtocolError("Chat stream has no consistent finish reason");
      const toolCalls = Array.from(calls).sort(([a], [b]) => a - b).map(([index, call], position) => {
        if (index !== position) throw new ModelProtocolError("Chat tool indexes are not contiguous");
        return { id: call.id, type: "function", function: { name: call.name, arguments: call.parts.join("") } };
      });
      return { events: [], turn: parseOpenAIChatTurn({ choices: [{ finish_reason: finish, message: { content: text.join(""), tool_calls: toolCalls } }], usage }) };
    }
    const record = streamRecord(event);
    if (record.usage != null) usage = requireRecord(record.usage, "Chat usage");
    const choices = requireArray(record.choices, "Chat choices");
    if (!choices.length) return { events: [] };
    if (choices.length !== 1) throw new ModelProtocolError("model turn expects one choice");
    const choice = requireRecord(choices[0], "Chat choice");
    if (choice.index !== 0 || finish) throw new ModelProtocolError("invalid Chat choice lifecycle");
    const delta = requireRecord(choice.delta, "Chat delta");
    const events: ModelStreamEvent[] = [];
    for (const field of ["content", "refusal"]) {
      if (delta[field] != null) {
        const part = streamString(delta[field]);
        text.push(part);
        if (part) events.push({ type: "text_delta", delta: part });
      }
    }
    if (delta.function_call) throw new ModelProtocolError("legacy function_call streaming is unsupported");
    if (delta.tool_calls !== undefined) {
      for (const value of requireArray(delta.tool_calls, "tool deltas")) {
        const item = requireRecord(value, "tool delta");
        const index = streamIndex(item.index);
        if (item.type !== undefined && item.type !== "function") throw new ModelProtocolError("unsupported Chat tool type");
        const fn = requireRecord(item.function, "tool function delta");
        const call = calls.get(index) ?? { parts: [] };
        call.id = immutableField(call.id, item.id);
        call.name = immutableField(call.name, fn.name);
        const argumentsDelta = fn.arguments === undefined ? undefined : streamString(fn.arguments);
        if (argumentsDelta !== undefined) call.parts.push(argumentsDelta);
        calls.set(index, call);
        events.push({ type: "tool_call_delta", index, id: call.id, name: call.name, argumentsDelta });
      }
    }
    if (choice.finish_reason != null) {
      finish = streamString(choice.finish_reason);
      if (finish !== "stop" && finish !== "tool_calls") throw new ModelProtocolError("Chat stream did not complete normally");
    }
    return { events };
  };
}
