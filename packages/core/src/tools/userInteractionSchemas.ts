export const askUserQuestionSchema = {
  type: "object",
  properties: {
    questions: {
      type: "array",
      items: {
        type: "object",
        properties: {
          question: { type: "string" },
          header: { type: "string" },
          options: {
            type: "array",
            items: {
              type: "object",
              properties: {
                label: { type: "string" },
                description: { type: "string" },
                preview: { type: "string" }
              },
              required: ["label", "description"],
              additionalProperties: false
            }
          },
          multiSelect: { type: "boolean" }
        },
        required: ["question", "header", "options"],
        additionalProperties: false
      }
    },
    answers: { type: "object", additionalProperties: { type: "string" } },
    annotations: { type: "object", additionalProperties: true },
    metadata: { type: "object", additionalProperties: true }
  },
  required: ["questions"],
  additionalProperties: false
};

export const userMessageSchema = {
  type: "object",
  properties: {
    message: { type: "string", description: "The message for the user. Markdown is supported." },
    attachments: { type: "array", items: { type: "string" } },
    status: { type: "string", enum: ["normal", "proactive"] }
  },
  required: ["message", "status"],
  additionalProperties: false
};
