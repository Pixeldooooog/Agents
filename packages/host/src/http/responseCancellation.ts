import type { ServerResponse } from "node:http";

/** A disconnected foreground request cancels its execution, including resumed approvals. */
export async function withResponseCancellation<T>(response: ServerResponse, run: (signal: AbortSignal) => Promise<T>): Promise<T> {
  const controller = new AbortController();
  const cancel = () => { if (!response.writableEnded) controller.abort(); };
  response.on("close", cancel);
  if (response.destroyed) cancel();
  try { return await run(controller.signal); }
  finally { response.off("close", cancel); }
}
