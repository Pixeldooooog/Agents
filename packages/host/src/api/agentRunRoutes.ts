import type { ServerResponse } from "node:http";
import type { HostServices } from "../services/hostServices.js";
import { readJson } from "../http/body.js";
import { approveRun } from "./agentRunApprovals.js";
import { runAgentChat, streamAgentChat } from "./agentRunExecution.js";
import { listModelProfiles, listRuns, sendRunDetail, sendRunTrace } from "./agentRunQueries.js";

const RUN_DETAIL_PATH = /^\/api\/v1\/agent\/runs\/([^/]+)$/;
const RUN_TRACE_PATH = /^\/api\/v1\/agent\/runs\/([^/]+)\/trace$/;
const RUN_APPROVAL_PATH = /^\/api\/v1\/agent\/runs\/([^/]+)\/approval$/;

export async function handleAgentRunRoute(services: HostServices, method: string, url: URL, request: AsyncIterable<unknown>, response: ServerResponse): Promise<boolean> {
  const path = url.pathname;
  if (method === "POST" && path === "/api/v1/agent/chat") return runAgentChat(services, await readJson(request as any), response);
  if (method === "POST" && path === "/api/v1/agent/chat/stream") return streamAgentChat(services, await readJson(request as any), response);
  if (method === "GET" && path === "/api/v1/agent/model-profiles") return listModelProfiles(services, response);
  if (method === "GET" && path === "/api/v1/agent/runs") return listRuns(services, url, response);

  const runId = matchPath(path, RUN_DETAIL_PATH);
  if (method === "GET" && runId) return sendRunDetail(services, runId, response);

  const traceRunId = matchPath(path, RUN_TRACE_PATH);
  if (method === "GET" && traceRunId) return sendRunTrace(services, traceRunId, response);

  const approvalRunId = matchPath(path, RUN_APPROVAL_PATH);
  if (method === "POST" && approvalRunId) return approveRun(services, approvalRunId, await readJson(request as any), response);

  return false;
}

function matchPath(path: string, pattern: RegExp): string | undefined {
  return pattern.exec(path)?.[1];
}
