import { defineTool, type RegisteredTool } from "../tools/toolContracts.js";
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

export const taskToolDefinitions: RegisteredTool[] = [
  defineTool({
    name: "task.create",
    description: "Create a persisted task for later execution.",
    risk: "medium",
    parameters: taskCreateSchema,
    requires: ["store"],
    handler: handleTaskCreate
  }),
  defineTool({
    name: "task.list",
    description: "List tasks visible to the current agent scope.",
    risk: "low",
    parameters: taskListSchema,
    requires: ["store"],
    handler: handleTaskList
  }),
  defineTool({
    name: "task.get",
    description: "Read a task and its steps by id or short id.",
    risk: "low",
    parameters: taskGetSchema,
    requires: ["store"],
    handler: handleTaskGet
  }),
  defineTool({
    name: "task.update",
    description: "Update a task title, input, status, or metadata.",
    risk: "medium",
    parameters: taskUpdateSchema,
    requires: ["store"],
    handler: handleTaskUpdate
  }),
  defineTool({
    name: "task.stop",
    description: "Cancel a task by id or short id.",
    risk: "medium",
    parameters: taskGetSchema,
    requires: ["store"],
    uses: ["taskRunner"],
    handler: handleTaskStop
  }),
  defineTool({
    name: "task.output",
    description: "Read accumulated step output for a task.",
    risk: "low",
    parameters: taskOutputSchema,
    requires: ["store"],
    handler: handleTaskOutput
  }),
  defineTool({
    name: "task.run",
    description: "Run an existing task or create and run a new task when a task runner is available.",
    risk: "medium",
    parameters: taskRunSchema,
    requires: ["store"],
    uses: ["taskRunner"],
    handler: handleTaskRun
  }),
  defineTool({
    name: "task.background",
    description: "Create a task record for background execution.",
    risk: "medium",
    parameters: taskRunSchema,
    requires: ["store"],
    uses: ["taskRunner"],
    handler: handleTaskBackground
  }),
  defineTool({
    name: "task.backgrounds",
    description: "List background task handles known to this TypeScript runtime.",
    risk: "low",
    parameters: { type: "object", properties: {} },
    requires: [],
    handler: handleTaskBackgrounds
  })
];
