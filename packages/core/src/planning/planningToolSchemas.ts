const todoItemSchema = {
  type: "object",
  properties: {
    content: { type: "string", description: "Imperative task description, for example Run tests." },
    status: { type: "string", enum: ["pending", "in_progress", "completed"] },
    activeForm: { type: "string", description: "Present-continuous form, for example Running tests." }
  },
  required: ["content", "status", "activeForm"],
  additionalProperties: false
};

export const todoWriteSchema = {
  type: "object",
  properties: {
    todos: { type: "array", items: todoItemSchema, description: "The full updated todo list for the current session." }
  },
  required: ["todos"],
  additionalProperties: false
};

export const planExitSchema = {
  type: "object",
  properties: {
    plan: { type: "string", description: "Concrete implementation plan to present before coding." },
    allowedPrompts: {
      type: "array",
      items: {
        type: "object",
        properties: {
          tool: { type: "string" },
          prompt: { type: "string" }
        },
        required: ["tool", "prompt"],
        additionalProperties: false
      }
    },
    planFilePath: { type: "string", description: "Optional plan file path supplied by SDK normalization." }
  },
  required: ["plan"]
};
