import { utf8Prefix } from "../execution/boundedOutput.js";

export const MAX_TOOL_OUTPUT_BYTES = 256 * 1024;

/** A truncated success remains a success: repeating a side effect is not recovery. */
export function boundedToolContent(payload: unknown): string {
  const content = typeof payload === "string" ? payload : JSON.stringify(payload) ?? "null";
  const bytes = Buffer.byteLength(content);
  if (bytes <= MAX_TOOL_OUTPUT_BYTES) return content;
  const buffer = Buffer.from(content);
  let previewBytes = MAX_TOOL_OUTPUT_BYTES - 512;
  for (;;) {
    const wrapped = JSON.stringify({ truncated: true, original_bytes: bytes,
      notice: "Output truncated. The operation was not retried. Request a smaller view when supported.",
      preview: utf8Prefix(buffer, previewBytes) });
    if (Buffer.byteLength(wrapped) <= MAX_TOOL_OUTPUT_BYTES) return wrapped;
    previewBytes = Math.floor(previewBytes / 2);
  }
}
