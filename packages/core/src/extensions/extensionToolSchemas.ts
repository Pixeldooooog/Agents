export const extensionDiscoverSchema = {
  type: "object",
  properties: {
    query: { type: "string" },
    max_results: { type: "integer", minimum: 1, maximum: 100 },
    include_prompt: { type: "boolean" }
  }
};

export const extensionInstallSchema = {
  type: "object",
  properties: { source: { type: "string" } },
  required: ["source"]
};

export const extensionNameSchema = {
  type: "object",
  properties: { name: { type: "string" } },
  required: ["name"]
};

export const skillInvokeSchema = {
  type: "object",
  properties: {
    skill: { type: "string" },
    args: { type: "string" },
    mode: { type: "string", enum: ["auto", "inline", "fork"] }
  },
  required: ["skill"],
  additionalProperties: false
};
