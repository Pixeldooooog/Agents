const timeout_ms = { type: "integer", minimum: 1 };
const text = { type: "string", minLength: 1 };
export const gitSchemas: Record<string, Record<string, unknown>> = {
  "git.status": { type: "object", properties: { timeout_ms } },
  "git.diff": { type: "object", properties: { timeout_ms } },
  "git.log": { type: "object", properties: { timeout_ms } },
  "git.show": { type: "object", properties: { timeout_ms, revision: text, ref: text } },
  "git.add": { type: "object", properties: { timeout_ms, path: text, paths: { type: "array", minItems: 1, items: text } } },
  "git.commit": { type: "object", properties: { timeout_ms, message: text }, required: ["message"] }
};
