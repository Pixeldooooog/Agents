import type { AgentResult } from "@agents/core";

export function responseStatusForRunResult(result: AgentResult): number {
  return result.status === "error" ? 500 : 200;
}
