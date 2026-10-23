export const scheduleCreateSchema = {
  type: "object",
  properties: {
    title: { type: "string" },
    input: { type: "string" },
    schedule: { type: "string", description: "Human-readable schedule or cron expression." },
    enabled: { type: "boolean" },
    metadata: { type: "object", additionalProperties: { type: "string" } }
  },
  required: ["title", "schedule"]
};

export const scheduleListSchema = {
  type: "object",
  properties: {
    enabled: { type: "boolean", description: "Optional enabled-state filter." },
    limit: { type: "integer", minimum: 1, maximum: 100 }
  }
};

export const scheduleDeleteSchema = {
  type: "object",
  properties: {
    schedule_id: { type: "string", description: "Schedule id or unambiguous short id." }
  },
  required: ["schedule_id"]
};

export const scheduleRunSchema = {
  type: "object",
  properties: {
    schedule_id: { type: "string", description: "Schedule id or unambiguous short id." },
    background: { type: "boolean", description: "Create a task record for asynchronous execution." }
  },
  required: ["schedule_id"]
};
