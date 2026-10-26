export const sessionStatusSchema = {
  type: "object",
  properties: {}
};

export const sessionExportSchema = {
  type: "object",
  properties: {
    path: { type: "string", description: "Workspace-relative export path. Defaults to .kevin/exports/<timestamp>.json or .md." },
    format: { type: "string", enum: ["json", "markdown"] },
    include_system: { type: "boolean" }
  }
};

export const sessionSummarySchema = {
  type: "object",
  properties: {
    include_system: { type: "boolean" },
    max_messages: { type: "integer", minimum: 1, maximum: 200 },
    max_chars: { type: "integer", minimum: 0, maximum: 20000 }
  }
};

export const contextTraceSchema = {
  type: "object",
  properties: {
    include_text: { type: "boolean" },
    max_chars: { type: "integer", minimum: 0, maximum: 20000 }
  }
};

export const contextCompactSchema = {
  type: "object",
  properties: {
    target_tokens: { type: "integer", minimum: 1 }
  }
};

export const contextRewindSchema = {
  type: "object",
  properties: {
    drop_last: { type: "integer", minimum: 1 }
  }
};
