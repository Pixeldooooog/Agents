import type { ServerResponse } from "node:http";
import { createScheduleRecord, resolveSchedule, scheduleScopeFromSpec, type JsonObject } from "@agents/core";
import type { HostServices } from "../services/hostServices.js";
import { queryNumber, queryValue, readJson } from "../http/body.js";
import { fail, ok, sendJson } from "../http/envelope.js";

export async function handleScheduleRoute(services: HostServices, method: string, url: URL, request: AsyncIterable<unknown>, response: ServerResponse): Promise<boolean> {
  const path = url.pathname;
  if (method === "POST" && path === "/api/v1/agent/schedules") return createSchedule(services, await readJson(request as any), response);
  if (method === "GET" && path === "/api/v1/agent/schedules") return listSchedules(services, url, response);
  if (method === "GET" && /^\/api\/v1\/agent\/schedules\/[^/]+$/.test(path)) return getSchedule(services, url, path.split("/").at(-1) || "", response);
  if (method === "DELETE" && /^\/api\/v1\/agent\/schedules\/[^/]+$/.test(path)) return deleteSchedule(services, url, path.split("/").at(-1) || "", response);
  if (method === "POST" && /^\/api\/v1\/agent\/schedules\/[^/]+\/run$/.test(path)) return runSchedule(services, url, path.split("/").at(-2) || "", await readJson(request as any), response);
  return false;
}

async function createSchedule(services: HostServices, payload: JsonObject, response: ServerResponse): Promise<true> {
  try {
    const title = requiredString(payload.title, "title");
    const schedule = requiredString(payload.schedule, "schedule");
    const spec = services.runs.specFromPayload({ message: String(payload.input || title), ...payload });
    const record = createScheduleRecord({
      spec,
      title,
      prompt: String(payload.input || title),
      schedule,
      enabled: payload.enabled === undefined ? true : Boolean(payload.enabled),
      metadata: { source: "api", ...stringMetadata(payload.metadata) }
    });
    sendJson(response, 200, ok({ schedule: await services.store.saveSchedule(record) }));
  } catch (error) {
    sendJson(response, 400, fail("400", error instanceof Error ? error.message : String(error), 400).body);
  }
  return true;
}

async function listSchedules(services: HostServices, url: URL, response: ServerResponse): Promise<true> {
  const spec = specForUrl(services, url);
  const schedules = await services.store.listSchedules({
    ...scheduleScopeFromSpec(spec),
    enabled: booleanQuery(url, "enabled"),
    limit: queryNumber(url, "limit", 50)
  });
  sendJson(response, 200, ok({ schedules, count: schedules.length, total: schedules.length }));
  return true;
}

async function getSchedule(services: HostServices, url: URL, scheduleId: string, response: ServerResponse): Promise<true> {
  try {
    sendJson(response, 200, ok({ schedule: await resolveScheduleForUrl(services, url, scheduleId) }));
  } catch (error) {
    sendJson(response, 404, fail("404", error instanceof Error ? error.message : String(error), 404).body);
  }
  return true;
}

async function deleteSchedule(services: HostServices, url: URL, scheduleId: string, response: ServerResponse): Promise<true> {
  try {
    const schedule = await resolveScheduleForUrl(services, url, scheduleId);
    await services.store.deleteSchedule(schedule.schedule_id);
    sendJson(response, 200, ok({ schedule, deleted: true }));
  } catch (error) {
    sendJson(response, 404, fail("404", error instanceof Error ? error.message : String(error), 404).body);
  }
  return true;
}

async function runSchedule(services: HostServices, url: URL, scheduleId: string, payload: JsonObject, response: ServerResponse): Promise<true> {
  try {
    const schedule = await resolveScheduleForUrl(services, url, scheduleId);
    const spec = services.runs.specFromPayload({
      message: schedule.input,
      tenant_id: schedule.tenant_id,
      user_id: schedule.user_id,
      agent_id: schedule.agent_id,
      workspace_id: schedule.workspace_id,
      ...payload
    });
    const task = await services.store.createTask(spec, schedule.input, schedule.title, { ...schedule.metadata, source: "schedule", schedule_id: schedule.schedule_id });
    const updatedSchedule = await services.store.markScheduleRun(schedule.schedule_id, task.task_id);
    sendJson(response, 200, ok({ schedule: updatedSchedule || schedule, task }));
  } catch (error) {
    sendJson(response, 404, fail("404", error instanceof Error ? error.message : String(error), 404).body);
  }
  return true;
}

async function resolveScheduleForUrl(services: HostServices, url: URL, scheduleId: string) {
  const schedules = await services.store.listSchedules({ ...scheduleScopeFromSpec(specForUrl(services, url)), limit: 100 });
  return resolveSchedule(schedules, scheduleId);
}

function specForUrl(services: HostServices, url: URL) {
  return services.runs.specFromPayload({
    message: "",
    tenant_id: queryValue(url, "tenant_id"),
    user_id: queryValue(url, "user_id"),
    agent_id: queryValue(url, "agent_id"),
    workspace_id: queryValue(url, "workspace_id")
  });
}

function booleanQuery(url: URL, name: string): boolean | undefined {
  const value = url.searchParams.get(name);
  if (value === null) return undefined;
  return ["1", "true", "yes", "on"].includes(value.trim().toLowerCase());
}

function requiredString(value: unknown, name: string): string {
  const text = String(value || "").trim();
  if (!text) throw new Error(`${name} is required`);
  return text;
}

function stringMetadata(value: unknown): Record<string, string> {
  if (!value || typeof value !== "object") return {};
  return Object.fromEntries(Object.entries(value).map(([key, entryValue]) => [String(key), String(entryValue)]));
}
