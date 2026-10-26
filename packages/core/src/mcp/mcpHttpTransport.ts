const MAX_RESPONSE_BYTES = 8 * 1024 * 1024;

/** The SDK owns JSON-RPC/SSE; the host bounds each HTTP response and forbids credential redirects. */
export async function boundedMcpFetch(input: string | URL | Request, init?: RequestInit): Promise<Response> {
  const response = await globalThis.fetch(input, { ...init, redirect: "error" });
  if (!response.body) return response;
  const declared = Number(response.headers.get("content-length"));
  if (declared > MAX_RESPONSE_BYTES) {
    await response.body.cancel();
    throw new Error("MCP response exceeds 8 MiB");
  }
  let bytes = 0;
  const body = response.body.pipeThrough(new TransformStream<Uint8Array, Uint8Array>({
    transform(chunk, controller) {
      bytes += chunk.byteLength;
      if (bytes > MAX_RESPONSE_BYTES) throw new Error("MCP response exceeds 8 MiB");
      controller.enqueue(chunk);
    }
  }));
  return new Response(body, { status: response.status, statusText: response.statusText, headers: response.headers });
}
