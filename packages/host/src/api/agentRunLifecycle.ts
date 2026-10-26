import type { AgentResult } from "@kevin/core";

export function responseStatusForRunResult(result: AgentResult): number {
  return result.status === "error" ? 500 : 200;
}
