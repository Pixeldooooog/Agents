import type { EventContract } from "../contracts/events.js";
import type { PersistedRunEvent, RuntimeEvent } from "../types/runtimeTypes.js";

const agentEventTypes: ReadonlySet<string> = new Set(["model_message", "text_delta"]);
const toolEventTypes: ReadonlySet<string> = new Set(["tool_start", "tool_result"]);

export function envelopeRunEvent(runId: string, sequence: number, event: RuntimeEvent): PersistedRunEvent {
  return {
    ...event,
    event_id: `evt_${crypto.randomUUID().replaceAll("-", "")}`,
    schema_version: 1,
    occurred_at: new Date().toISOString(),
    actor: runEventActor(event.type),
    run_id: runId,
    sequence
  };
}

function runEventActor(type: string): EventContract["actor"] {
  if (agentEventTypes.has(type)) return "agent";
  if (toolEventTypes.has(type)) return "tool";
  return "system";
}
