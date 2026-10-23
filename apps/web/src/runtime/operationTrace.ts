import type { OperationEvent } from "../types/runtimeTypes";
import { projectRunTrace } from "./operationTraceProjector";
import type { createApiClient } from "./apiClient";

type ApiClient = ReturnType<typeof createApiClient>;

export async function loadOperationTrace(api: ApiClient, runId: string): Promise<OperationEvent[]> {
  if (!runId) return [];
  try {
    return projectRunTrace(await api.runTrace(runId), runId);
  } catch {
    return [];
  }
}
