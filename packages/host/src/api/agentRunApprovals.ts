import type { ServerResponse } from "node:http";
import { AgentRunServiceError, type RunApprovalPayload } from "@kevin/core";
import type { HostServices } from "../services/hostServices.js";
import { fail, ok, sendJson } from "../http/envelope.js";
import { responseStatusForRunResult } from "./agentRunLifecycle.js";

export async function approveRun(services: HostServices, runId: string, payload: RunApprovalPayload, response: ServerResponse): Promise<true> {
  try {
    const { result, events } = await services.runs.resumeApproval(runId, Boolean(payload.approved));
    sendJson(response, responseStatusForRunResult(result), ok({ ...result, run_id: runId, events }));
  } catch (error) {
    if (error instanceof AgentRunServiceError) {
      sendJson(response, error.statusCode, fail(String(error.statusCode), error.message, error.statusCode).body);
      return true;
    }
    throw error;
  }
  return true;
}
