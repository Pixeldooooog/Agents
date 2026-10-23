import { AgentSdkClient } from "./agentSdkClient.js";
import type { SdkJsonlChunk } from "./sdkJsonl.js";
import type { SdkJsonlTransport } from "./sdkJsonlTransport.js";
import type { SdkMessage, SdkResultMessage } from "./sdkMessages.js";
import type { SdkProtocolRunnerOptions } from "./sdkProtocolRunner.js";
import type { SdkForkSessionOptions, SdkForkSessionResult } from "./sdkSessionMutations.js";
import type { SdkGetSessionMessagesOptions, SdkListSessionsOptions, SdkSessionInfo } from "./sdkSessionRecords.js";
import type { SdkSession } from "./sdkSession.js";
import type { SdkQueryOptions } from "./sdkTypes.js";
import type { SdkControlRequestMessage, SdkControlResponseMessage, SdkWireInputMessage, SdkWireMessage } from "./sdkControlTypes.js";

export type SdkClientProviderOptions = {
  client?: AgentSdkClient;
  repoRoot?: string;
};

export type SdkQueryHelperOptions = SdkQueryOptions & SdkClientProviderOptions;
export type SdkProtocolHelperOptions = SdkProtocolRunnerOptions & SdkClientProviderOptions;
export type SdkListSessionsHelperOptions = SdkListSessionsOptions & SdkClientProviderOptions;
export type SdkGetSessionMessagesHelperOptions = SdkGetSessionMessagesOptions & SdkClientProviderOptions;
export type SdkForkSessionHelperOptions = SdkForkSessionOptions & SdkClientProviderOptions;

export async function createSession(options: SdkQueryHelperOptions = {}): Promise<SdkSession> {
  const client = await sdkClientForHelper(options);
  return client.createSession(stripClientProviderOptions(options));
}

export async function resumeSession(
  sessionId: string,
  options: SdkQueryHelperOptions = {}
): Promise<SdkSession> {
  const client = await sdkClientForHelper(options);
  return client.resumeSession(sessionId, stripClientProviderOptions(options));
}

export async function* query(
  promptText: string,
  options: SdkQueryHelperOptions = {}
): AsyncIterable<SdkMessage> {
  const client = await sdkClientForHelper(options);
  for await (const message of client.query(promptText, stripClientProviderOptions(options))) yield message;
}

export async function prompt(
  promptText: string,
  options: SdkQueryHelperOptions = {}
): Promise<SdkResultMessage> {
  const client = await sdkClientForHelper(options);
  return client.prompt(promptText, stripClientProviderOptions(options));
}

export async function listSessions(
  options: SdkListSessionsHelperOptions = {}
): Promise<SdkSessionInfo[]> {
  const client = await sdkClientForHelper(options);
  return client.listSessions(stripClientProviderOptions(options));
}

export async function getSessionInfo(
  sessionId: string,
  options: SdkClientProviderOptions = {}
): Promise<SdkSessionInfo | undefined> {
  const client = await sdkClientForHelper(options);
  return client.getSessionInfo(sessionId);
}

export async function getSessionMessages(
  sessionId: string,
  options: SdkGetSessionMessagesHelperOptions = {}
): Promise<SdkMessage[]> {
  const client = await sdkClientForHelper(options);
  return client.getSessionMessages(sessionId, stripClientProviderOptions(options));
}

export async function renameSession(
  sessionId: string,
  title: string,
  options: SdkClientProviderOptions = {}
): Promise<void> {
  const client = await sdkClientForHelper(options);
  await client.renameSession(sessionId, title);
}

export async function tagSession(
  sessionId: string,
  tag: string | undefined,
  options: SdkClientProviderOptions = {}
): Promise<void> {
  const client = await sdkClientForHelper(options);
  await client.tagSession(sessionId, tag);
}

export async function forkSession(
  sessionId: string,
  options: SdkForkSessionHelperOptions = {}
): Promise<SdkForkSessionResult> {
  const client = await sdkClientForHelper(options);
  return client.forkSession(sessionId, stripClientProviderOptions(options));
}

export async function handleControlRequest(
  message: SdkControlRequestMessage | Record<string, unknown>,
  options: SdkProtocolHelperOptions = {}
): Promise<SdkControlResponseMessage> {
  const client = await sdkClientForHelper(options);
  return client.handleControlRequest(message, stripClientProviderOptions(options));
}

export async function* runWireMessages(
  messages: AsyncIterable<SdkWireInputMessage> | Iterable<SdkWireInputMessage>,
  options: SdkProtocolHelperOptions = {}
): AsyncIterable<SdkWireMessage> {
  const client = await sdkClientForHelper(options);
  for await (const message of client.runWireMessages(messages, stripClientProviderOptions(options))) yield message;
}

export function runStdin(
  messages: AsyncIterable<SdkWireInputMessage> | Iterable<SdkWireInputMessage>,
  options: SdkProtocolHelperOptions = {}
): AsyncIterable<SdkWireMessage> {
  return runWireMessages(messages, options);
}

export async function* runJsonlChunks(
  chunks: AsyncIterable<SdkJsonlChunk> | Iterable<SdkJsonlChunk>,
  options: SdkProtocolHelperOptions = {}
): AsyncIterable<string> {
  const client = await sdkClientForHelper(options);
  for await (const line of client.runJsonlChunks(chunks, stripClientProviderOptions(options))) yield line;
}

export function runStdinJsonl(
  chunks: AsyncIterable<SdkJsonlChunk> | Iterable<SdkJsonlChunk>,
  options: SdkProtocolHelperOptions = {}
): AsyncIterable<string> {
  return runJsonlChunks(chunks, options);
}

export async function runJsonlTransport(
  transport: SdkJsonlTransport,
  options: SdkProtocolHelperOptions = {}
): Promise<void> {
  const client = await sdkClientForHelper(options);
  await client.runJsonlTransport(transport, stripClientProviderOptions(options));
}

export function unstableV2CreateSession(options: SdkQueryHelperOptions = {}): Promise<SdkSession> {
  return createSession(options);
}

export function unstableV2ResumeSession(
  sessionId: string,
  options: SdkQueryHelperOptions = {}
): Promise<SdkSession> {
  return resumeSession(sessionId, options);
}

export function unstableV2Prompt(
  promptText: string,
  options: SdkQueryHelperOptions = {}
): Promise<SdkResultMessage> {
  return prompt(promptText, options);
}

export const fork_session = forkSession;
export const get_session_info = getSessionInfo;
export const get_session_messages = getSessionMessages;
export const handle_control_request = handleControlRequest;
export const list_sessions = listSessions;
export const rename_session = renameSession;
export const run_jsonl_transport = runJsonlTransport;
export const run_stdin = runStdin;
export const run_stdin_jsonl = runStdinJsonl;
export const tag_session = tagSession;
export const unstable_v2_create_session = unstableV2CreateSession;
export const unstable_v2_prompt = unstableV2Prompt;
export const unstable_v2_resume_session = unstableV2ResumeSession;

async function sdkClientForHelper(options: SdkClientProviderOptions = {}): Promise<AgentSdkClient> {
  return options.client || AgentSdkClient.create(options.repoRoot);
}

function stripClientProviderOptions<T extends SdkClientProviderOptions>(options: T): Omit<T, keyof SdkClientProviderOptions> {
  const { client: _client, repoRoot: _repoRoot, ...rest } = options;
  return rest;
}
