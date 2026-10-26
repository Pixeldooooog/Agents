import type { ServerResponse } from "node:http";
import { activeProfileName, buildModelProfiles, buildOperationFrames } from "@kevin/core";
import type { HostServices } from "../services/hostServices.js";
import { queryNumber, queryValue } from "../http/body.js";
import { fail, ok, sendJson } from "../http/envelope.js";

export async function listModelProfiles(services: HostServices, response: ServerResponse): Promise<true> {
  const profiles = buildModelProfiles(services.settings);
  const activeSpec = services.runs.specFromPayload({ message: "" });
  sendJson(response, 200, ok({ active_profile: activeProfileName(profiles, activeSpec), profiles }));
  return true;
}

export async function listRuns(services: HostServices, url: URL, response: ServerResponse): Promise<true> {
  const data = await services.store.listRuns({
    limit: queryNumber(url, "limit", 50),
    tenant_id: queryValue(url, "tenant_id"),
    user_id: queryValue(url, "user_id"),
    agent_id: queryValue(url, "agent_id")
  });
  sendJson(response, 200, ok({ runs: data }));
  return true;
}

export async function sendRunDetail(services: HostServices, runId: string, response: ServerResponse): Promise<true> {
  const run = await services.store.loadRun(runId);
  if (!run) sendJson(response, 404, fail("404", `run not found: ${runId}`, 404).body);
  else sendJson(response, 200, ok(run));
  return true;
}

export async function sendRunTrace(services: HostServices, runId: string, response: ServerResponse): Promise<true> {
  const run = await services.store.loadRun(runId);
  if (!run) {
    sendJson(response, 404, fail("404", `run not found: ${runId}`, 404).body);
    return true;
  }
  sendJson(response, 200, ok({
    run_id: runId,
    spans: [],
    approvals: [],
    sandbox_leases: [],
    artifacts: [],
    sandbox_events: [],
    sandbox_snapshots: [],
    operation_frames: buildOperationFrames(runId, run.events)
  }));
  return true;
}
