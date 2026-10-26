const editProperties = { old_text: { type: "string" }, new_text: { type: "string" }, replace_all: { type: "boolean" } };
export const patchSchema = { type: "object", properties: {
  path: { type: "string", minLength: 1 }, create: { type: "boolean" }, ...editProperties,
  edits: { type: "array", minItems: 1, items: { type: "object", properties: editProperties } }
}, required: ["path"] };
