import { defineTool, type RegisteredTool } from "./toolContracts.js";
import { askUserQuestion, sendUserMessage } from "./userInteractionPayloads.js";
import { askUserQuestionSchema, userMessageSchema } from "./userInteractionSchemas.js";

export const userInteractionToolDefinitions: RegisteredTool[] = [
  defineTool({
    name: "user.ask",
    description: "Ask the user multiple-choice questions.",
    risk: "low",
    parameters: askUserQuestionSchema,
    requires: [],
    handler: async (_context, args) => askUserQuestion(args)
  }),
  defineTool({
    name: "user.message",
    description: "Send a message to the user.",
    risk: "low",
    parameters: userMessageSchema,
    requires: [],
    handler: sendUserMessage
  })
];
