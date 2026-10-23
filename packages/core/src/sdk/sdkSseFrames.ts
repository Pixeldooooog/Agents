import { formatSdkTransportUrl, parseSdkTransportUrl, withSdkTransportQueryParam } from "./sdkTransportUrls.js";

export type SdkSseFrame = {
  event?: string;
  id?: string;
  data?: string;
};

export function parseSseFrames(buffer: string): { frames: SdkSseFrame[]; rest: string } {
  const frames: SdkSseFrame[] = [];
  let position = 0;
  while (true) {
    const delimiter = findSseFrameDelimiter(buffer, position);
    if (!delimiter) break;
    const rawFrame = buffer.slice(position, delimiter.index);
    position = delimiter.index + delimiter.length;
    if (!rawFrame.trim()) continue;
    const frame: SdkSseFrame = {};
    let isComment = false;
    for (const line of rawFrame.split(/\r\n|\n|\r/)) {
      if (line.startsWith(":")) {
        isComment = true;
        continue;
      }
      const colonIndex = line.indexOf(":");
      if (colonIndex === -1) continue;
      const field = line.slice(0, colonIndex);
      const value = line.slice(colonIndex + 1).replace(/^ /, "");
      if (field === "event") frame.event = value;
      if (field === "id") frame.id = value;
      if (field === "data") frame.data = frame.data ? `${frame.data}\n${value}` : value;
    }
    if (frame.data || isComment) frames.push(frame);
  }
  return { frames, rest: buffer.slice(position) };
}

export function deriveSseStreamUrl(url: string): string {
  const streamUrl = parseSdkTransportUrl(url);
  if (streamUrl.scheme === "wss:") streamUrl.scheme = "https:";
  if (streamUrl.scheme === "ws:") streamUrl.scheme = "http:";
  streamUrl.path = `${streamUrl.path.replace(/\/+$/, "")}/worker/events/stream`;
  return formatSdkTransportUrl(streamUrl);
}

export function deriveSsePostUrl(sseUrl: string): string {
  const postUrl = parseSdkTransportUrl(sseUrl);
  if (postUrl.path.endsWith("/stream")) postUrl.path = postUrl.path.slice(0, -"/stream".length);
  postUrl.query = "";
  postUrl.fragment = "";
  return formatSdkTransportUrl(postUrl);
}

export function withSseFromSequenceParam(url: string, sequenceNumber: number): string {
  return withSdkTransportQueryParam(url, "from_sequence_num", String(sequenceNumber));
}

export const parse_sse_frames = parseSseFrames;
export const derive_sse_stream_url = deriveSseStreamUrl;
export const derive_sse_post_url = deriveSsePostUrl;

function findSseFrameDelimiter(buffer: string, start: number): { index: number; length: number } | undefined {
  const delimiters = ["\r\n\r\n", "\n\n", "\r\r"];
  const matches = delimiters
    .map((delimiter) => ({ index: buffer.indexOf(delimiter, start), length: delimiter.length }))
    .filter((match) => match.index !== -1);
  return matches.sort((left, right) => left.index - right.index)[0];
}
