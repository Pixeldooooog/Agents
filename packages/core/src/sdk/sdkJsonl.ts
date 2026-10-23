import type { SdkStdinMessage, SdkWireMessage } from "./sdkControlTypes.js";
import { validateSdkStdinMessage, validateSdkStdoutMessage, validateSdkWireMessage } from "./sdkWireValidation.js";

export type SdkJsonlChunk = string | Uint8Array;

export class SdkJsonlDecodeError extends Error {
  constructor(readonly line: string, reason: string) {
    super(`Error parsing SDK JSONL line: ${line}: ${reason}`);
    this.name = "SdkJsonlDecodeError";
  }
}

export class SdkStdinDecodeError extends Error {
  constructor(readonly line: string, reason: string) {
    super(`Error parsing streaming input line: ${line}: ${reason}`);
    this.name = "SdkStdinDecodeError";
  }
}

export class SdkJsonlDecoder {
  private readonly decoder = new BufferedJsonlDecoder(decodeSdkJsonlLine);

  decode(chunk: SdkJsonlChunk): SdkWireMessage[] {
    return this.decoder.decode(chunk);
  }

  flush(): SdkWireMessage[] {
    return this.decoder.flush();
  }
}

export class SdkStdinJsonlDecoder {
  private readonly decoder = new BufferedJsonlDecoder(decodeSdkStdinJsonlLine);

  decode(chunk: SdkJsonlChunk): SdkStdinMessage[] {
    return this.decoder.decode(chunk);
  }

  flush(): SdkStdinMessage[] {
    return this.decoder.flush();
  }
}

export function encodeSdkJsonlMessage(message: SdkWireMessage): string {
  return `${ndjsonSafeStringify(message)}\n`;
}

export function encodeSdkStdoutMessage(message: unknown): string {
  return `${ndjsonSafeStringify(validateSdkStdoutMessage(message))}\n`;
}

export function decodeSdkJsonlLine(line: string): SdkWireMessage | undefined {
  if (!line) return undefined;
  let value: unknown;
  try {
    value = JSON.parse(line);
  } catch (error) {
    throw new SdkJsonlDecodeError(line, errorMessage(error));
  }
  try {
    return validateSdkWireMessage(value);
  } catch (error) {
    throw new SdkJsonlDecodeError(line, errorMessage(error));
  }
}

export function decodeSdkStdinJsonlLine(line: string): SdkStdinMessage | undefined {
  if (!line) return undefined;
  let value: unknown;
  try {
    value = JSON.parse(line);
  } catch (error) {
    throw new SdkStdinDecodeError(line, errorMessage(error));
  }
  try {
    return validateSdkStdinMessage(value);
  } catch (error) {
    throw new SdkStdinDecodeError(line, errorMessage(error));
  }
}

export function ndjsonSafeStringify(value: unknown): string {
  const text = JSON.stringify(value);
  if (text === undefined) throw new TypeError("SDK JSONL frame must be JSON serializable");
  return text.replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
}

export const encode_stdout_message = encodeSdkStdoutMessage;
export const ndjson_safe_dumps = ndjsonSafeStringify;

type JsonlLineDecoder<T> = (line: string) => T | undefined;

class BufferedJsonlDecoder<T> {
  private buffer = "";

  constructor(private readonly decodeLine: JsonlLineDecoder<T>) {}

  decode(chunk: SdkJsonlChunk): T[] {
    this.buffer += chunkToText(chunk);
    const messages: T[] = [];
    while (true) {
      const newlineIndex = this.buffer.indexOf("\n");
      if (newlineIndex === -1) return messages;
      const line = this.buffer.slice(0, newlineIndex);
      this.buffer = this.buffer.slice(newlineIndex + 1);
      const message = this.decodeLine(line);
      if (message) messages.push(message);
    }
  }

  flush(): T[] {
    if (!this.buffer) return [];
    const line = this.buffer;
    this.buffer = "";
    const message = this.decodeLine(line);
    return message ? [message] : [];
  }
}

function chunkToText(chunk: SdkJsonlChunk): string {
  return typeof chunk === "string" ? chunk : new TextDecoder().decode(chunk);
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
