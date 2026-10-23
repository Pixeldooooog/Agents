import type { ServerResponse } from "node:http";
import type { HostServices } from "../services/hostServices.js";
import { handleMemoryRoute } from "./memoryRoutes.js";
import { handleScheduleRoute } from "./scheduleRoutes.js";
import { handleAgentRunRoute } from "./agentRunRoutes.js";
import { handleAgentTaskRoute } from "./agentTaskRoutes.js";

export async function handleAgentRoute(services: HostServices, method: string, url: URL, request: AsyncIterable<unknown>, response: ServerResponse): Promise<boolean> {
  if (await handleAgentRunRoute(services, method, url, request, response)) return true;
  if (await handleAgentTaskRoute(services, method, url, request, response)) return true;
  if (await handleScheduleRoute(services, method, url, request, response)) return true;
  if (await handleMemoryRoute(services, method, url, request, response)) return true;
  return false;
}
