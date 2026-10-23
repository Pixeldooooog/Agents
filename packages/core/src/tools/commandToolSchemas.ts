export const commandDiscoverSchema = {
  type: "object",
  properties: {
    query: { type: "string" },
    max_results: { type: "integer", minimum: 1, maximum: 100 }
  }
};

export const commandRenderSchema = {
  type: "object",
  properties: {
    name: { type: "string" },
    arguments: { type: "string" }
  },
  required: ["name"]
};

export const commandReadSchema = {
  type: "object",
  properties: {
    name: { type: "string" },
    max_bytes: { type: "integer", minimum: 1, maximum: 200000 }
  },
  required: ["name"]
};

export const commandSaveSchema = {
  type: "object",
  properties: {
    name: { type: "string" },
    content: { type: "string" },
    description: { type: "string" },
    argument_hint: { type: "string" },
    aliases: { type: "array", items: { type: "string" } },
    category: { type: "string" },
    overwrite: { type: "boolean" }
  },
  required: ["name", "content"]
};

export const commandDeleteSchema = {
  type: "object",
  properties: {
    name: { type: "string" }
  },
  required: ["name"]
};
