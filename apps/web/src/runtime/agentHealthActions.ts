import type { Setter } from "solid-js";
import type { ActivityEvent } from "../types/runtimeTypes";
import type { createApiClient } from "./apiClient";
import { errorText } from "./sessionUtils";
import { copy } from "../copy";

type ApiClient = ReturnType<typeof createApiClient>;

type AgentHealthActionsOptions = {
  api: () => ApiClient;
  setHealth: Setter<string>;
  record: (kind: ActivityEvent["kind"], title: string, detail: string, status: ActivityEvent["status"]) => number;
  updateActivity: (id: number, patch: Partial<ActivityEvent>) => void;
};

export function createAgentHealthActions(options: AgentHealthActionsOptions) {
  const checkHealth = async () => {
    const id = options.record("system", copy.activity.healthProbe, "GET /health", "running");
    try {
      await options.api().health();
      options.setHealth("online");
      options.updateActivity(id, { status: "done", detail: "200 OK" });
    } catch (error) {
      options.setHealth("offline");
      options.updateActivity(id, { status: "error", detail: errorText(error) });
    }
  };

  return { checkHealth };
}
