export const worktreeEnterSchema = {
  type: "object",
  properties: {
    name: { type: "string" },
    pr_number: { type: "integer", minimum: 1 }
  },
  additionalProperties: false
};

export const worktreeExitSchema = {
  type: "object",
  properties: {
    action: { type: "string", enum: ["keep", "remove"] },
    discard_changes: { type: "boolean" }
  },
  required: ["action"],
  additionalProperties: false
};
