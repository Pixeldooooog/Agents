import type { ServerResponse } from "node:http";
import type { AgentChatPayload } from "@agents/core";
import type { HostServices } from "../services/hostServices.js";
import { queryValue, readJson } from "../http/body.js";
import { fail, ok, sendJson } from "../http/envelope.js";

const TASK_DETAIL_PATH = /^\/api\/v1\/agent\/tasks\/([^/]+)$/;
const TASK_RUN_PATH = /^\/api\/v1\/agent\/tasks\/([^/]+)\/run$/;
const TASK_CANCEL_PATH = /^\/api\/v1\/agent\/tasks\/([^/]+)\/cancel$/;

export async function handleAgentTaskRoute(services: HostServices, method: string, url: URL, request: AsyncIterable<unknown>, response: ServerResponse): Promise<boolean> {
  const path = url.pathname;
  if (method === "POST" && path === "/api/v1/agent/tasks") return createTask(services, await readJson(request as any), response);
  if (method === "GET" && path === "/api/v1/agent/tasks") return listTasks(services, url, response);

  const taskId = matchPath(path, TASK_DETAIL_PATH);
  if (method === "GET" && taskId) return getTask(services, taskId, response);

  const runTaskId = matchPath(path, TASK_RUN_PATH);
  if (method === "POST" && runTaskId) return runTask(services, runTaskId, response);

  const cancelTaskId = matchPath(path, TASK_CANCEL_PATH);
  if (method === "POST" && cancelTaskId) return cancelTask(services, cancelTaskId, response);

  return false;
}

async function createTask(services: HostServices, payload: AgentChatPayload, response: ServerResponse): Promise<true> {
  const task = await services.tasks.create(payload);
  sendJson(response, 200, ok(task));
  return true;
}

async function listTasks(services: HostServices, url: URL, response: ServerResponse): Promise<true> {
  const tasks = await services.store.listTasks({
    tenant_id: queryValue(url, "tenant_id"),
    user_id: queryValue(url, "user_id"),
    agent_id: queryValue(url, "agent_id")
  });
  sendJson(response, 200, ok({ tasks }));
  return true;
}

async function getTask(services: HostServices, taskId: string, response: ServerResponse): Promise<true> {
  const task = await services.store.loadTask(taskId);
  if (!task) sendJson(response, 404, fail("404", `task not found: ${taskId}`, 404).body);
  else sendJson(response, 200, ok({ task, steps: await services.store.listSteps(taskId) }));
  return true;
}

async function runTask(services: HostServices, taskId: string, response: ServerResponse): Promise<true> {
  try {
    const result = await services.tasks.run(taskId);
    const run = await services.store.loadRun(result.result.run_id);
    sendJson(response, 200, ok({
      ...result,
      run,
      result: {
        status: result.result.status,
        content: result.result.content,
        events: result.result.events
      }
    }));
  } catch (error) {
    sendJson(response, 404, fail("404", error instanceof Error ? error.message : String(error), 404).body);
  }
  return true;
}

async function cancelTask(services: HostServices, taskId: string, response: ServerResponse): Promise<true> {
  try {
    sendJson(response, 200, ok(await services.tasks.cancel(taskId)));
  } catch (error) {
    sendJson(response, 404, fail("404", error instanceof Error ? error.message : String(error), 404).body);
  }
  return true;
}

function matchPath(path: string, pattern: RegExp): string | undefined {
  return pattern.exec(path)?.[1];
}
