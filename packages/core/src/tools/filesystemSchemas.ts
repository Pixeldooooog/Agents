const path = { type: "string", minLength: 1 };
export const filesystemReadSchema = { type: "object", properties: {
  path, offset: { type: "integer", minimum: 0 }, limit: { type: "integer", minimum: 0 }
}, required: ["path"] };
export const filesystemListSchema = { type: "object", properties: {
  path, limit: { type: "integer", minimum: 1, maximum: 10000 }
} };
export const filesystemWriteSchema = { type: "object", properties: { path, content: { type: "string" } }, required: ["path", "content"] };
export const filesystemDeleteSchema = { type: "object", properties: { path, recursive: { type: "boolean" }, force: { type: "boolean" } }, required: ["path"] };
export const filesystemMoveSchema = { type: "object", properties: { source: path, destination: path }, required: ["source", "destination"] };
