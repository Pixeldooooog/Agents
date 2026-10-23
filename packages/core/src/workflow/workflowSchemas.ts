export const workflowValidateSchema = {
  type: "object",
  properties: {
    workflow_id: { type: "string" },
    nodes: { type: "array", items: { type: "object" } },
    edges: { type: "array", items: { type: "object" } },
    metadata: { type: "object", additionalProperties: { type: "string" } }
  },
  required: ["nodes"]
};

export const workflowRunSchema = {
  type: "object",
  properties: { ...workflowValidateSchema.properties, stop_on_error: { type: "boolean" } },
  required: ["nodes"]
};

export const workflowSaveSchema = {
  type: "object",
  properties: { name: { type: "string" }, ...workflowValidateSchema.properties, overwrite: { type: "boolean" } },
  required: ["name", "nodes"]
};
