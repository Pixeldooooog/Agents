import type { ToolDefinition } from "../tools/toolContracts.js";
import {
  handleTaskBackground,
  handleTaskBackgrounds,
  handleTaskCreate,
  handleTaskGet,
  handleTaskList,
  handleTaskOutput,
  handleTaskRun,
  handleTaskStop,
  handleTaskUpdate
} from "./taskToolHandlers.js";
import { taskCreateSchema, taskGetSchema, taskListSchema, taskOutputSchema, taskRunSchema, taskUpdateSchema } from "./taskToolSchemas.js";

export const taskToolDefinitions: ToolDefinition[] = [
  {
    name: "task.create",
    description: "Create a persisted task for later execution.",
    risk: "medium",
    parameters: taskCreateSchema,
    handler: handleTaskCreate
  },
  {
    name: "task.list",
    description: "List tasks visible to the current agent scope.",
    risk: "low",
    parameters: taskListSchema,
    handler: handleTaskList
  },
  {
    name: "task.get",
    description: "Read a task and its steps by id or short id.",
    risk: "low",
    parameters: taskGetSchema,
    handler: handleTaskGet
  },
  {
    name: "task.update",
    description: "Update a task title, input, status, or metadata.",
    risk: "medium",
    parameters: taskUpdateSchema,
    handler: handleTaskUpdate
  },
  {
    name: "task.stop",
    description: "Cancel a task by id or short id.",
    risk: "medium",
    parameters: taskGetSchema,
    handler: handleTaskStop
  },
  {
    name: "task.output",
    description: "Read accumulated step output for a task.",
    risk: "low",
    parameters: taskOutputSchema,
    handler: handleTaskOutput
  },
  {
    name: "task.run",
    description: "Run an existing task or create and run a new task when a task runner is available.",
    risk: "medium",
    parameters: taskRunSchema,
    handler: handleTaskRun
  },
  {
    name: "task.background",
    description: "Create a task record for background execution.",
    risk: "medium",
    parameters: taskRunSchema,
    handler: handleTaskBackground
  },
  {
    name: "task.backgrounds",
    description: "List background task handles known to this TypeScript runtime.",
    risk: "low",
    parameters: { type: "object", properties: {} },
    handler: handleTaskBackgrounds
  }
];
