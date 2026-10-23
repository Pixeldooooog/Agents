import type { ToolDefinition } from "../tools/toolContracts.js";
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

export const scheduleToolDefinitions: ToolDefinition[] = [
  {
    name: "schedule.create",
    description: "Create a persisted schedule for a prompt.",
    risk: "medium",
    parameters: scheduleCreateSchema,
    handler: scheduleCreate
  },
  {
    name: "schedule.list",
    description: "List schedules visible to the current agent scope.",
    risk: "low",
    parameters: scheduleListSchema,
    handler: scheduleList
  },
  {
    name: "schedule.delete",
    description: "Delete a persisted schedule by id or short id.",
    risk: "medium",
    parameters: scheduleDeleteSchema,
    handler: scheduleDelete
  },
  {
    name: "schedule.run",
    description: "Create a task from a persisted schedule and record its last run metadata.",
    risk: "medium",
    parameters: scheduleRunSchema,
    handler: scheduleRun
  }
];
