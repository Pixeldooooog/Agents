/** Retains a UTF-8-safe prefix while draining the entire stream. */
export class BoundedOutput {
  private chunks: Buffer[] = [];
  private retained = 0;
  bytes = 0;

  constructor(readonly maxBytes: number) {}

  append(chunk: Buffer | string): void {
    const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    this.bytes += buffer.length;
    const remaining = Math.max(0, this.maxBytes - this.retained);
    if (remaining) {
      const prefix = Buffer.from(buffer.subarray(0, remaining));
      this.chunks.push(prefix);
      this.retained += prefix.length;
    }
  }

  get truncated(): boolean { return this.bytes > this.retained; }
  text(): string { return utf8Prefix(Buffer.concat(this.chunks), this.retained); }
}

export function utf8Prefix(buffer: Buffer, maxBytes: number): string {
  let end = Math.max(0, Math.min(buffer.length, Math.floor(maxBytes)));
  // A decoder would replace a partial final code point, potentially exceeding the byte limit.
  let start = end - 1;
  while (start >= 0 && (buffer[start] & 0xc0) === 0x80) start--;
  if (start >= 0) {
    const lead = buffer[start];
    const size = lead >= 0xf0 ? 4 : lead >= 0xe0 ? 3 : lead >= 0xc0 ? 2 : 1;
    if (start + size > end) end = start;
  }
  const text = buffer.subarray(0, end).toString("utf8");
  // Invalid source bytes decode to replacement characters, which can expand in UTF-8.
  return Buffer.byteLength(text) > maxBytes ? utf8Prefix(Buffer.from(text), maxBytes) : text;
}
