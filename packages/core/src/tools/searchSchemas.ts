const shared = { path: { type: "string" }, limit: { type: "integer", minimum: 1, maximum: 10000 } };
export const grepSchema = { type: "object", properties: { ...shared,
  pattern: { type: "string", minLength: 1 }, flags: { type: "string" },
  case_sensitive: { anyOf: [{ type: "boolean" }, { enum: ["true", "false"] }] }
}, required: ["pattern"] };
export const globSchema = { type: "object", properties: { ...shared, pattern: { type: "string" } } };
