import type { RunRecord, RuntimeEvent } from "../types/runtimeTypes.js";
import type { JsonStateStore } from "../store/jsonStateStore.js";
import type { SdkMessage } from "./sdkMessages.js";
import { sdkMessagesFromRuntimeEvent } from "./sdkEventProjection.js";
import { sdkResultMessageFromRunRecord } from "./sdkResultMessages.js";
import { compactSdkSessionReplayEvents } from "./sdkSessionCompaction.js";
import { sdkSystemInitMessageFromRun } from "./sdkSystemMessages.js";

export type SdkSessionInfo = {
  sessionId: string;
  session_id: string;
  summary: string;
  createdAt: number;
  created_at: number;
  lastModified: number;
  last_modified: number;
  firstPrompt: string;
  first_prompt: string;
  runCount: number;
  status: string;
  customTitle?: string;
  custom_title: string;
  cwd?: string;
  tag?: string;
  latestRunId: string;
  latest_run_id: string;
  runIds: string[];
  run_ids: string[];
  metadata: Record<string, unknown>;
};

type SdkSessionInfoAliasKey =
  | "session_id"
  | "created_at"
  | "last_modified"
  | "first_prompt"
  | "custom_title"
  | "latest_run_id"
  | "run_ids";

export type SdkListSessionsOptions = {
  limit?: number;
  offset?: number;
  tenantId?: string;
  tenant_id?: string;
  userId?: string;
  user_id?: string;
  agentId?: string;
  agent_id?: string;
  cwd?: string;
};

export type SdkGetSessionMessagesOptions = {
  limit?: number;
  offset?: number;
  includeSystemMessages?: boolean;
  include_system_messages?: boolean;
};

const sessionListRunLimit = 200;

export async function listSdkSessions(
  store: JsonStateStore,
  options: SdkListSessionsOptions = {}
): Promise<SdkSessionInfo[]> {
  const runs = await store.listRuns({
    limit: sessionListRunLimit,
    tenant_id: stringOption(options.tenantId ?? options.tenant_id),
    user_id: stringOption(options.userId ?? options.user_id),
    agent_id: stringOption(options.agentId ?? options.agent_id)
  });
  const filteredRuns = options.cwd ? runs.filter((run) => runCwd(run) === options.cwd) : runs;
  const offset = normalizeOffset(options.offset);
  const limit = normalizeLimit(options.limit, 50, 200, { allowZero: true });
  const infos = sessionInfosFromRuns(filteredRuns).slice(offset);
  return limit === 0 ? infos : infos.slice(0, limit);
}

export async function getSdkSessionInfo(store: JsonStateStore, sessionId: string): Promise<SdkSessionInfo | undefined> {
  return sessionInfoFromRuns(await sessionRuns(store, sessionId));
}

export async function getSdkSessionMessages(
  store: JsonStateStore,
  sessionId: string,
  options: SdkGetSessionMessagesOptions = {}
): Promise<SdkMessage[]> {
  const runs = await listSdkSessionRuns(store, sessionId);
  const isCompactedReplay = runs.some((run) => run.events.some((event) => event.type === "compact_boundary"));
  const includeSystemMessages = booleanOption(options.includeSystemMessages ?? options.include_system_messages, true);
  const messages = isCompactedReplay
    ? sdkMessagesForCompactedRuns(runs, sessionId, includeSystemMessages)
    : runs.flatMap((run) => sdkMessagesForRun(run, sessionId, replayEventsForRun(run), includeSystemMessages));
  const filteredMessages = includeSystemMessages ? messages : messages.filter((message) => message.type !== "system");
  const offset = normalizeOffset(options.offset);
  const limit = normalizeLimit(options.limit, 200, 1000, { allowZero: true });
  const offsetMessages = filteredMessages.slice(offset);
  return limit === 0 ? offsetMessages : offsetMessages.slice(0, limit);
}

export async function listSdkSessionRuns(store: JsonStateStore, sessionId: string): Promise<RunRecord[]> {
  const resolvedSessionId = String(sessionId || "").trim();
  if (!resolvedSessionId) return [];
  const runsById = new Map<string, RunRecord>();
  const directRun = await store.loadRun(resolvedSessionId);
  if (directRun) runsById.set(directRun.run_id, directRun);
  for (const run of await store.listRuns({ limit: sessionListRunLimit })) {
    if (sessionIdForRun(run) === resolvedSessionId || run.run_id === resolvedSessionId) {
      runsById.set(run.run_id, run);
    }
  }
  return sortRunsChronologically([...runsById.values()]);
}

function sessionInfosFromRuns(runs: RunRecord[]): SdkSessionInfo[] {
  const grouped = new Map<string, RunRecord[]>();
  for (const run of runs) {
    const sessionId = sessionIdForRun(run);
    if (!sessionId) continue;
    grouped.set(sessionId, [...(grouped.get(sessionId) || []), run]);
  }
  return [...grouped.entries()]
    .map(([sessionId, sessionRunsForId]) => sessionInfoFromRuns(sessionRunsForId, sessionId))
    .filter((info): info is SdkSessionInfo => Boolean(info))
    .sort((left, right) => right.lastModified - left.lastModified);
}

function sessionInfoFromRuns(runs: RunRecord[], explicitSessionId = ""): SdkSessionInfo | undefined {
  if (!runs.length) return undefined;
  const ordered = sortRunsChronologically(runs);
  const firstRun = ordered[0];
  const latestRun = latestUpdatedRun(ordered);
  const sessionId = explicitSessionId || sessionIdForRun(latestRun);
  if (!sessionId) return undefined;
  const customTitle = String(latestRun.metadata.sdk_title || latestRun.metadata.custom_title || latestRun.metadata.title || "");
  const firstPrompt = firstNonEmpty(ordered.map(userPromptForRun));
  const cwd = firstNonEmpty([...ordered].reverse().map(runCwd));
  return withSessionInfoAliases({
    sessionId,
    summary: customTitle || firstPrompt || latestRun.run_id,
    createdAt: timestampMillis(firstRun.created_at),
    lastModified: timestampMillis(Math.max(...ordered.map((run) => run.updated_at))),
    firstPrompt,
    runCount: ordered.length,
    status: latestRun.status,
    ...(customTitle ? { customTitle } : {}),
    ...(cwd ? { cwd } : {}),
    ...(latestRun.metadata.sdk_tag || latestRun.metadata.tag ? { tag: String(latestRun.metadata.sdk_tag || latestRun.metadata.tag) } : {}),
    latestRunId: latestRun.run_id,
    runIds: ordered.map((run) => run.run_id),
    metadata: { ...latestRun.metadata, run_count: ordered.length }
  });
}

function withSessionInfoAliases(info: Omit<SdkSessionInfo, SdkSessionInfoAliasKey>): SdkSessionInfo {
  Object.defineProperties(info, {
    session_id: { get: () => info.sessionId },
    created_at: { get: () => info.createdAt },
    last_modified: { get: () => info.lastModified },
    first_prompt: { get: () => info.firstPrompt || "" },
    custom_title: { get: () => info.customTitle || "" },
    latest_run_id: { get: () => info.latestRunId },
    run_ids: { get: () => [...info.runIds] }
  });
  return info as SdkSessionInfo;
}

async function sessionRuns(store: JsonStateStore, sessionId: string): Promise<RunRecord[]> {
  return listSdkSessionRuns(store, sessionId);
}

function sdkMessagesForCompactedRuns(
  runs: RunRecord[],
  sessionId: string,
  includeSystemMessages: boolean
): SdkMessage[] {
  const entries = compactSdkSessionReplayEvents(
    runs.flatMap((run) => replayEventsForRun(run).map((event) => ({ run, event })))
  );
  const initializedRunIds = new Set<string>();
  const runsWithProjectedResult = new Set<string>();
  const includedRuns = new Map<string, RunRecord>();
  const messages: SdkMessage[] = [];
  for (const entry of entries) {
    includedRuns.set(entry.run.run_id, entry.run);
    const projectedMessages = sdkMessagesFromRuntimeEvent(entry.run.run_id, sessionId, entry.event);
    const isFirstRunEntry = !initializedRunIds.has(entry.run.run_id);
    if (isFirstRunEntry) {
      messages.push(...sdkReplayRunPrelude(entry.run, sessionId, projectedMessages, includeSystemMessages));
      initializedRunIds.add(entry.run.run_id);
    }
    messages.push(...(isFirstRunEntry
      ? projectedMessages.filter((message) => message.type !== "user_message")
      : projectedMessages));
    if (projectedMessages.some((message) => message.type === "result")) runsWithProjectedResult.add(entry.run.run_id);
  }
  for (const run of includedRuns.values()) {
    if (!runsWithProjectedResult.has(run.run_id)) messages.push(sdkResultMessageFromRunRecord(run, sessionId));
  }
  return messages;
}

function sdkReplayRunPrelude(
  run: RunRecord,
  sessionId: string,
  projectedMessages: SdkMessage[],
  includeSystemMessages: boolean
): SdkMessage[] {
  const projectedUserMessages = projectedMessages.filter((message) => message.type === "user_message");
  return [
    ...(includeSystemMessages ? [sdkSystemInitMessageFromRun(run, sessionId)] : []),
    ...(projectedUserMessages.length ? projectedUserMessages : [syntheticUserMessageForRun(run, sessionId)]),
    runStartedMessage(run, sessionId)
  ];
}

function sdkMessagesForRun(
  run: RunRecord,
  sessionId: string,
  replayEvents: RuntimeEvent[],
  includeSystemMessages: boolean
): SdkMessage[] {
  const projectedMessages = replayEvents.flatMap((event) => sdkMessagesFromRuntimeEvent(run.run_id, sessionId, event));
  const projectedUserMessages = projectedMessages.filter((message) => message.type === "user_message");
  const projectedNonUserMessages = projectedMessages.filter((message) => message.type !== "user_message");
  const hasProjectedResult = projectedMessages.some((message) => message.type === "result");
  return [
    ...(includeSystemMessages ? [sdkSystemInitMessageFromRun(run, sessionId)] : []),
    ...(projectedUserMessages.length ? projectedUserMessages : [syntheticUserMessageForRun(run, sessionId)]),
    runStartedMessage(run, sessionId),
    ...projectedNonUserMessages,
    ...(hasProjectedResult ? [] : [sdkResultMessageFromRunRecord(run, sessionId)])
  ];
}

function replayEventsForRun(run: RunRecord): RuntimeEvent[] {
  return run.events.filter((event) => event.type !== "run_created");
}

function runStartedMessage(run: RunRecord, sessionId: string): SdkMessage {
  return {
    type: "run_started",
    runId: run.run_id,
    sessionId,
    createdAt: run.created_at
  };
}

function syntheticUserMessageForRun(run: RunRecord, sessionId: string): SdkMessage {
  return {
    type: "user_message",
    uuid: run.metadata.sdk_user_message_uuid || `${run.run_id}:user`,
    sessionId,
    content: userPromptForRun(run)
  };
}

function userPromptForRun(run: RunRecord): string {
  return String(run.metadata.sdk_first_prompt || run.metadata.sdk_prompt || run.metadata.first_prompt || run.metadata.prompt || "");
}

function runCwd(run: RunRecord): string {
  return String(run.metadata.sdk_cwd || run.metadata.cwd || "");
}

function firstNonEmpty(values: string[]): string {
  return values.find((value) => value.trim()) || "";
}

function latestUpdatedRun(runs: RunRecord[]): RunRecord {
  return [...runs].sort((left, right) => right.updated_at - left.updated_at)[0];
}

function sessionIdForRun(run: RunRecord): string {
  return String(
    run.metadata.sdk_session_id
      || run.metadata.file_history_session_id
      || run.metadata.fileHistorySessionId
      || run.run_id
  );
}

function sortRunsChronologically(runs: RunRecord[]): RunRecord[] {
  return runs
    .map((run, index) => ({ run, index }))
    .sort((left, right) => left.run.created_at - right.run.created_at || right.index - left.index)
    .map((item) => item.run);
}

function timestampMillis(timestampSeconds: number): number {
  return timestampSeconds * 1000;
}

function normalizeOffset(value: unknown): number {
  if (value === undefined || value === null || value === "") return 0;
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 0) {
    throw new Error("SDK option offset must be a non-negative integer");
  }
  return parsed;
}

function normalizeLimit(value: unknown, fallback: number, maximum: number, options: { allowZero?: boolean } = {}): number {
  if (value === undefined || value === null || value === "") return fallback;
  const parsed = Number(value);
  const minimum = options.allowZero ? 0 : 1;
  if (!Number.isInteger(parsed) || parsed < minimum || parsed > maximum) {
    throw new Error(`SDK option limit must be an integer between ${minimum} and ${maximum}`);
  }
  return parsed;
}

function stringOption(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed || undefined;
}

function booleanOption(value: unknown, fallback: boolean): boolean {
  if (typeof value === "boolean") return value;
  return fallback;
}
