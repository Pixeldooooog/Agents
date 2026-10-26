export const shellRunSchema = { type: "object", properties: {
  command: { type: "string", minLength: 1 },
  timeout_ms: { type: "integer", minimum: 1 },
  run_in_background: { type: "boolean" },
  dangerouslyDisableSandbox: { const: false },
  description: { type: "string" }
}, required: ["command"] };
export const shellOutputSchema = { type: "object", properties: {
  task_id: { type: "string", minLength: 1 }, block: { type: "boolean" },
  timeout_seconds: { type: "number", minimum: 0, maximum: 120 },
  max_bytes: { type: "integer", minimum: 1, maximum: 200000 }
}, required: ["task_id"] };
export const shellKillSchema = { type: "object", properties: { task_id: { type: "string", minLength: 1 } }, required: ["task_id"] };
