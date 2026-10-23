import type { ToolDefinition } from "./toolContracts.js";
import { askUserQuestion, sendUserMessage } from "./userInteractionPayloads.js";
import { askUserQuestionSchema, userMessageSchema } from "./userInteractionSchemas.js";

export const userInteractionToolDefinitions: ToolDefinition[] = [
  {
    name: "user.ask",
    description: "Ask the user multiple-choice questions.",
    risk: "low",
    parameters: askUserQuestionSchema,
    handler: async (_context, args) => askUserQuestion(args)
  },
  {
    name: "user.message",
    description: "Send a message to the user.",
    risk: "low",
    parameters: userMessageSchema,
    handler: sendUserMessage
  }
];
