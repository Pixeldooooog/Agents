import { withResponseCancellation } from "../http/responseCancellation.js";
import type { ServerResponse } from "node:http";
import { AgentRunServiceError, type AgentChatPayload } from "@kevin/core";
import type { HostServices } from "../services/hostServices.js";
import { fail, ok, sendJson, sendSse } from "../http/envelope.js";
import { responseStatusForRunResult } from "./agentRunLifecycle.js";

export async function runAgentChat(services: HostServices, payload: AgentChatPayload, response: ServerResponse): Promise<true> {
  try {
    const { run, result, events } = await withResponseCancellation(response, signal => services.runs.runPayload(payload, { signal }));
    sendJson(response, responseStatusForRunResult(result), ok({ ...result, run_id: run.run_id, events }));
  } catch (error) {
    if (!(error instanceof AgentRunServiceError)) throw error;
    sendJson(response, error.statusCode, fail(String(error.statusCode), error.message, error.statusCode).body);
  }
  return true;
}

export async function streamAgentChat(services: HostServices, payload: AgentChatPayload, response: ServerResponse): Promise<true> {
  response.writeHead(200, { "Content-Type": "text/event-stream; charset=utf-8", "Cache-Control": "no-cache", Connection: "keep-alive" });
  await withResponseCancellation(response, signal => services.runs.runPayload(payload, {
    signal,
    stream: true,
    afterRunStarted: (run) => sendSse(response, "run_created", run.events[0]),
    onEvent: (event) => sendSse(response, event.type, event)
  }));
  response.end();
  return true;
}
