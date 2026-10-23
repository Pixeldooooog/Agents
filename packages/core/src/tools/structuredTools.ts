import type { JsonObject } from "../types/jsonTypes.js";
import type { ToolDefinition } from "./toolContracts.js";

export const structuredToolDefinitions: ToolDefinition[] = [
  {
    name: "structured.output",
    description: "Return structured output in the requested format.",
    risk: "low",
    parameters: { type: "object", properties: {}, additionalProperties: true },
    handler: async (_context, args: JsonObject) => ({
      data: "Structured output provided successfully",
      structured_output: { ...args }
    })
  }
];
