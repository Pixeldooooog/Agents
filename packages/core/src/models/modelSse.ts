import { ModelProtocolError } from "./modelErrors.js";

export type SseEvent = { event: string; data: string };
const MAX_EVENT_CHARS = 1024 * 1024;

/** Incremental SSE framing; protocol payloads remain the adapter's responsibility. */
export async function* readSseEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<SseEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let lineParts: string[] = [];
  let lineSize = 0;
  let eventSize = 0;
  let data: string[] = [];
  let event = "message";
  let afterCR = false;

  function finishLine(): SseEvent | undefined {
    const line = lineParts.join("");
    lineParts = [];
    lineSize = 0;
    if (!line) {
      const result = data.length ? { event, data: data.join("\n") } : undefined;
      data = [];
      event = "message";
      eventSize = 0;
      return result;
    }
    eventSize += line.length + 1;
    if (eventSize > MAX_EVENT_CHARS) throw new ModelProtocolError("SSE event exceeds size limit");
    const colon = line.indexOf(":");
    const field = colon < 0 ? line : line.slice(0, colon);
    let value = colon < 0 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "data") data.push(value);
    if (field === "event") event = value;
  }

  try {
    while (true) {
      const { done, value } = await reader.read();
      let text: string;
      try { text = done ? decoder.decode() : decoder.decode(value, { stream: true }); }
      catch { throw new ModelProtocolError("SSE contains invalid UTF-8"); }
      let start = 0;
      for (let i = 0; i < text.length; i++) {
        const char = text[i];
        if (afterCR && char === "\n") { afterCR = false; start = i + 1; continue; }
        afterCR = false;
        if (char !== "\r" && char !== "\n") continue;
        const part = text.slice(start, i);
        lineParts.push(part);
        lineSize += part.length;
        if (lineSize + eventSize > MAX_EVENT_CHARS) throw new ModelProtocolError("SSE event exceeds size limit");
        const frame = finishLine();
        if (frame) yield frame;
        afterCR = char === "\r";
        start = i + 1;
      }
      const tail = text.slice(start);
      if (tail) { lineParts.push(tail); lineSize += tail.length; }
      if (lineSize + eventSize > MAX_EVENT_CHARS) throw new ModelProtocolError("SSE event exceeds size limit");
      if (done) {
        // SSE dispatch requires a blank line; never promote a truncated frame at EOF.
        if (lineSize || data.length) throw new ModelProtocolError("SSE ended inside an event");
        return;
      }
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
