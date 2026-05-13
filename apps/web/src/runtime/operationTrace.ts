import type { OperationEvent } from "../types";
import { projectRunTrace } from "./operationProjector";
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
