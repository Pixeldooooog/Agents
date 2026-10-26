import type { StateStore } from "../ports/stateStore.js";
import { specFromPayload } from "../types/agentTypes.js";
import type { RunRecord, RuntimeEvent } from "../types/runtimeTypes.js";
import { eventMatchesMessageId } from "./sdkEventIdentity.js";
import { migrateFileHistoryEventsForSession } from "./sdkFileHistoryMigration.js";
import { listSdkSessionRuns } from "./sdkSessionRecords.js";

export type SdkForkSessionOptions = {
  title?: string;
  upToMessageId?: string;
  up_to_message_id?: string;
};

export type SdkForkSessionResult = {
  sessionId: string;
  session_id: string;
  runIds: string[];
  run_ids: string[];
};

export async function renameSdkSession(store: StateStore, sessionId: string, title: string): Promise<void> {
  const customTitle = title.trim();
  if (!customTitle) throw new Error("session title cannot be empty");
  await updateSdkSessionMetadata(store, sessionId, { sdk_title: customTitle });
}

export async function tagSdkSession(store: StateStore, sessionId: string, tag: string | undefined): Promise<void> {
  await updateSdkSessionMetadata(store, sessionId, { sdk_tag: String(tag || "").trim() });
}

export async function forkSdkSession(
  store: StateStore,
  sessionId: string,
  options: SdkForkSessionOptions = {}
): Promise<SdkForkSessionResult> {
  const runs = await listSdkSessionRuns(store, sessionId);
  if (!runs.length) throw new Error(`session not found: ${sessionId}`);
  const upToMessageId = stringOption(options.upToMessageId ?? options.up_to_message_id);
  const forkedSessionId = newSdkSessionId();
  const runIds: string[] = [];
  for (const run of runs) {
    const events = await migrateFileHistoryEventsForSession(eventsForFork(run.events, upToMessageId), {
      runs,
      sourceSessionId: sessionId,
      targetSessionId: forkedSessionId
    });
    const metadata = forkedRunMetadata(run, forkedSessionId, sessionId, options.title);
    const forkedRun = await store.startRun(specFromPayload({ message: "", ...run.spec, metadata }));
    for (const event of events) await store.recordEvent(forkedRun.run_id, event);
    await store.setPendingApproval(forkedRun.run_id, run.pending_approval);
    await store.finishRun(forkedRun.run_id, run.status);
    runIds.push(forkedRun.run_id);
    if (upToMessageId && events.some((event) => eventMatchesMessageId(event, upToMessageId))) break;
  }
  return withForkSessionResultAliases({ sessionId: forkedSessionId, runIds });
}

function withForkSessionResultAliases(info: Omit<SdkForkSessionResult, "session_id" | "run_ids">): SdkForkSessionResult {
  Object.defineProperties(info, {
    session_id: { get: () => info.sessionId },
    run_ids: { get: () => [...info.runIds] }
  });
  return info as SdkForkSessionResult;
}

async function updateSdkSessionMetadata(
  store: StateStore,
  sessionId: string,
  metadata: Record<string, string>
): Promise<void> {
  const runs = await listSdkSessionRuns(store, sessionId);
  if (!runs.length) throw new Error(`session not found: ${sessionId}`);
  for (const run of runs) await store.updateRunMetadata(run.run_id, metadata);
}

function forkedRunMetadata(
  run: RunRecord,
  forkedSessionId: string,
  sourceSessionId: string,
  title: string | undefined
): Record<string, string> {
  const customTitle = String(title || "").trim();
  return {
    ...run.metadata,
    sdk_session_id: forkedSessionId,
    sdk_file_history_session_id: forkedSessionId,
    sdk_forked_from_session_id: sourceSessionId,
    sdk_forked_from_run_id: run.run_id,
    ...(customTitle ? { sdk_title: customTitle } : {})
  };
}

function eventsForFork(events: RuntimeEvent[], upToMessageId: string | undefined): RuntimeEvent[] {
  const result: RuntimeEvent[] = [];
  for (const event of events) {
    if (event.type === "run_created") continue;
    result.push(cloneRuntimeEvent(event));
    if (upToMessageId && eventMatchesMessageId(event, upToMessageId)) break;
  }
  return result;
}

function cloneRuntimeEvent(event: RuntimeEvent): RuntimeEvent {
  return JSON.parse(JSON.stringify(event)) as RuntimeEvent;
}

function newSdkSessionId(): string {
  return `session_${crypto.randomUUID().replaceAll("-", "")}`;
}

function stringOption(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}
