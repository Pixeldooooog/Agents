import type { JsonObject } from "../types/jsonTypes.js";
import { defineTool, type RegisteredTool } from "./toolContracts.js";

export const structuredToolDefinitions: RegisteredTool[] = [
  defineTool({
    name: "structured.output",
    description: "Return structured output in the requested format.",
    risk: "low",
    parameters: { type: "object", properties: {}, additionalProperties: true },
    requires: [],
    handler: async (_context, args: JsonObject) => ({
      data: "Structured output provided successfully",
      structured_output: { ...args }
    })
  })
];
