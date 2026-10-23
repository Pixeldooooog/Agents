import { randomUUID } from "node:crypto";

export function ccrWorkerRegisterPayload(workerEpoch: number): Record<string, unknown> {
  return {
    worker_status: "idle",
    worker_epoch: workerEpoch,
    external_metadata: { pending_action: null, task_summary: null }
  };
}

export function ccrClientEvent(message: Record<string, unknown>): Record<string, unknown> {
  const payload = { ...message };
  if (typeof payload.uuid !== "string") payload.uuid = randomUUID();
  return { payload };
}

export function ccrInternalEvent(
  eventType: string,
  payload: Record<string, unknown>,
  options: { isCompaction?: boolean; agentId?: string } = {}
): Record<string, unknown> {
  const event: Record<string, unknown> = {
    payload: {
      type: eventType,
      ...payload,
      uuid: typeof payload.uuid === "string" ? payload.uuid : randomUUID()
    }
  };
  if (options.isCompaction) event.is_compaction = true;
  if (options.agentId) event.agent_id = options.agentId;
  return event;
}

export function ccrDeliveryUpdates(updates: Record<string, unknown>[]): Array<Record<string, unknown>> {
  return updates.map((update) => ({ event_id: update.eventId ?? update.event_id, status: update.status }));
}
