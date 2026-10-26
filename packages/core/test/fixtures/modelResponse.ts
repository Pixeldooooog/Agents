/** Shared happy-path provider fixtures for SDK tests; malformed-stream tests use raw events. */
export function modelStreamResponse(payload: {
  choices?: Array<{ message: { content?: string | null; tool_calls?: Array<{ id: string; type?: string; function: { name: string; arguments: string } }> } }>;
  content?: Array<{ type: string; text: string }>;
  usage?: Record<string, unknown>;
}): Response {
  const frames: unknown[] = [];
  if (payload.choices) {
    const message = payload.choices[0].message;
    frames.push({ choices: [{ index: 0, delta: {
      content: message.content ?? "",
      ...(message.tool_calls ? { tool_calls: message.tool_calls.map((call, index) => ({ ...call, index })) } : {})
    }, finish_reason: null }] });
    frames.push({ choices: [{ index: 0, delta: {}, finish_reason: message.tool_calls?.length ? "tool_calls" : "stop" }] });
    if (payload.usage) frames.push({ choices: [], usage: payload.usage });
  } else {
    frames.push({ type: "message_start", message: { role: "assistant", content: [], usage: { input_tokens: 1 } } });
    for (const [index, block] of (payload.content ?? []).entries()) {
      frames.push({ type: "content_block_start", index, content_block: { type: "text", text: "" } });
      frames.push({ type: "content_block_delta", index, delta: { type: "text_delta", text: block.text } });
      frames.push({ type: "content_block_stop", index });
    }
    frames.push({ type: "message_delta", delta: { stop_reason: "end_turn" }, usage: { output_tokens: 1 } });
    frames.push({ type: "message_stop" });
  }
  return new Response(frames.map(frame => `data: ${JSON.stringify(frame)}\n\n`).join("") + (payload.choices ? "data: [DONE]\n\n" : ""), { headers: { "Content-Type": "text/event-stream" } });
}
