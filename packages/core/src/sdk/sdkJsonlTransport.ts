import {
  encodeSdkJsonlMessage,
  encodeSdkStdoutMessage,
  SdkJsonlDecoder,
  SdkStdinJsonlDecoder,
  type SdkJsonlChunk
} from "./sdkJsonl.js";
import type { SdkStdinMessage, SdkWireMessage } from "./sdkControlTypes.js";

export type SdkJsonlTransport = {
  read(): Promise<SdkJsonlChunk | undefined>;
  write(data: string): Promise<void>;
  close(): Promise<void> | void;
};

export async function* readSdkJsonlTransport(transport: SdkJsonlTransport): AsyncIterable<SdkWireMessage> {
  const decoder = new SdkJsonlDecoder();
  while (true) {
    const chunk = await transport.read();
    if (chunk === undefined) break;
    for (const message of decoder.decode(chunk)) yield message;
  }
  for (const message of decoder.flush()) yield message;
}

export async function* readSdkStdinJsonlTransport(transport: SdkJsonlTransport): AsyncIterable<SdkStdinMessage> {
  const decoder = new SdkStdinJsonlDecoder();
  while (true) {
    const chunk = await transport.read();
    if (chunk === undefined) break;
    for (const message of decoder.decode(chunk)) yield message;
  }
  for (const message of decoder.flush()) yield message;
}

export function writeSdkJsonlTransport(transport: SdkJsonlTransport, message: SdkWireMessage): Promise<void> {
  return transport.write(encodeSdkJsonlMessage(message));
}

export function writeSdkStdoutJsonlTransport(transport: SdkJsonlTransport, message: unknown): Promise<void> {
  return transport.write(encodeSdkStdoutMessage(message));
}
