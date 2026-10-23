import type { TaskStatus } from "../types/taskTypes.js";

export const taskStatusValues: TaskStatus[] = ["created", "running", "paused", "awaiting_approval", "finished", "error", "canceled"];

export const taskCreateSchema = {
  type: "object",
  properties: {
    title: { type: "string" },
    input: { type: "string" },
    metadata: { type: "object", additionalProperties: { type: "string" } }
  }
};

export const taskListSchema = {
  type: "object",
  properties: {
    status: { type: "string", enum: ["", ...taskStatusValues] },
    agent_id: { type: "string" },
    limit: { type: "integer", minimum: 1, maximum: 100 }
  }
};

export const taskGetSchema = {
  type: "object",
  properties: {
    task_id: { type: "string", description: "Task id or unambiguous short id." }
  },
  required: ["task_id"]
};

export const taskUpdateSchema = {
  type: "object",
  properties: {
    task_id: { type: "string", description: "Task id or unambiguous short id." },
    status: { type: "string", enum: ["", ...taskStatusValues] },
    title: { type: "string" },
    input: { type: "string" },
    metadata: { type: "object", additionalProperties: true }
  },
  required: ["task_id"]
};

export const taskOutputSchema = {
  type: "object",
  properties: {
    task_id: { type: "string", description: "Task id or unambiguous short id." },
    max_bytes: { type: "integer", minimum: 1, maximum: 200000 }
  },
  required: ["task_id"]
};

export const taskRunSchema = {
  type: "object",
  properties: {
    task_id: { type: "string", description: "Optional existing task id or short id." },
    title: { type: "string" },
    input: { type: "string" },
    metadata: { type: "object", additionalProperties: { type: "string" } },
    step_name: { type: "string" }
  }
};
