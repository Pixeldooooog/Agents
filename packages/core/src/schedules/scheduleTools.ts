import { defineTool, type RegisteredTool } from "../tools/toolContracts.js";
import {
  scheduleCreate,
  scheduleDelete,
  scheduleList,
  scheduleRun
} from "./scheduleToolHandlers.js";
import {
  scheduleCreateSchema,
  scheduleDeleteSchema,
  scheduleListSchema,
  scheduleRunSchema
} from "./scheduleToolSchemas.js";

export const scheduleToolDefinitions: RegisteredTool[] = [
  defineTool({
    name: "schedule.create",
    description: "Create a persisted schedule for a prompt.",
    risk: "medium",
    parameters: scheduleCreateSchema,
    requires: ["store"],
    handler: scheduleCreate
  }),
  defineTool({
    name: "schedule.list",
    description: "List schedules visible to the current agent scope.",
    risk: "low",
    parameters: scheduleListSchema,
    requires: ["store"],
    handler: scheduleList
  }),
  defineTool({
    name: "schedule.delete",
    description: "Delete a persisted schedule by id or short id.",
    risk: "medium",
    parameters: scheduleDeleteSchema,
    requires: ["store"],
    handler: scheduleDelete
  }),
  defineTool({
    name: "schedule.run",
    description: "Create a task from a persisted schedule and record its last run metadata.",
    risk: "medium",
    parameters: scheduleRunSchema,
    requires: ["store"],
    handler: scheduleRun
  })
];
