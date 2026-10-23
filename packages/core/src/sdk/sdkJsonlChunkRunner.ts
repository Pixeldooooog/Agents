import type { SdkStdinMessage, SdkWireMessage } from "./sdkControlTypes.js";
import { encodeSdkStdoutMessage, SdkJsonlDecoder, SdkStdinJsonlDecoder, type SdkJsonlChunk } from "./sdkJsonl.js";
import type { SdkProtocolRunnerOptions } from "./sdkProtocolRunner.js";

export type SdkWireMessageRunner = (
  messages: AsyncIterable<SdkWireMessage>,
  options?: SdkProtocolRunnerOptions
) => AsyncIterable<SdkWireMessage>;

export async function* runSdkJsonlChunks(
  chunks: AsyncIterable<SdkJsonlChunk> | Iterable<SdkJsonlChunk>,
  runner: SdkWireMessageRunner,
  options: SdkProtocolRunnerOptions = {}
): AsyncIterable<string> {
  for await (const message of runner(sdkStdinMessagesFromJsonlChunks(chunks), options)) {
    yield encodeSdkStdoutMessage(message);
  }
}

export async function* sdkWireMessagesFromJsonlChunks(
  chunks: AsyncIterable<SdkJsonlChunk> | Iterable<SdkJsonlChunk>
): AsyncIterable<SdkWireMessage> {
  const decoder = new SdkJsonlDecoder();
  for await (const chunk of asyncChunks(chunks)) {
    for (const message of decoder.decode(chunk)) yield message;
  }
  for (const message of decoder.flush()) yield message;
}

export async function* sdkStdinMessagesFromJsonlChunks(
  chunks: AsyncIterable<SdkJsonlChunk> | Iterable<SdkJsonlChunk>
): AsyncIterable<SdkStdinMessage> {
  const decoder = new SdkStdinJsonlDecoder();
  for await (const chunk of asyncChunks(chunks)) {
    for (const message of decoder.decode(chunk)) yield message;
  }
  for (const message of decoder.flush()) yield message;
}

export const iter_stdin_jsonl = sdkStdinMessagesFromJsonlChunks;

async function* asyncChunks(chunks: AsyncIterable<SdkJsonlChunk> | Iterable<SdkJsonlChunk>): AsyncIterable<SdkJsonlChunk> {
  if (Symbol.asyncIterator in chunks) {
    for await (const chunk of chunks as AsyncIterable<SdkJsonlChunk>) yield chunk;
    return;
  }
  for (const chunk of chunks as Iterable<SdkJsonlChunk>) yield chunk;
}
