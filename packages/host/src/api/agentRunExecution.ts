import type { ServerResponse } from "node:http";
import type { AgentChatPayload } from "@kevin/core";
import type { HostServices } from "../services/hostServices.js";
import { ok, sendJson, sendSse } from "../http/envelope.js";
import { responseStatusForRunResult } from "./agentRunLifecycle.js";

export async function runAgentChat(services: HostServices, payload: AgentChatPayload, response: ServerResponse): Promise<true> {
  const { run, result, events } = await services.runs.runPayload(payload);
  sendJson(response, responseStatusForRunResult(result), ok({ ...result, run_id: run.run_id, events }));
  return true;
}

export async function streamAgentChat(services: HostServices, payload: AgentChatPayload, response: ServerResponse): Promise<true> {
  response.writeHead(200, { "Content-Type": "text/event-stream; charset=utf-8", "Cache-Control": "no-cache", Connection: "keep-alive" });
  await services.runs.runPayload(payload, {
    stream: true,
    afterRunStarted: (run) => sendSse(response, "run_created", run.events[0]),
    onEvent: (event) => sendSse(response, event.type, event)
  });
  response.end();
  return true;
}
