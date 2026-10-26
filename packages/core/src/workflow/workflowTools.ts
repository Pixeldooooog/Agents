import { defineTool, type RegisteredTool } from "../tools/toolContracts.js";
import {
  handleWorkflowDelete,
  handleWorkflowRead,
  handleWorkflowRun,
  handleWorkflowRunSaved,
  handleWorkflowSave,
  handleWorkflowTemplates,
  handleWorkflowValidate
} from "./workflowHandlers.js";
import { workflowRunSchema, workflowSaveSchema, workflowValidateSchema } from "./workflowSchemas.js";

export const workflowToolDefinitions: RegisteredTool[] = [
  defineTool({
    name: "workflow.templates",
    description: "List saved workflow templates.",
    risk: "low",
    parameters: { type: "object", properties: { query: { type: "string" }, max_results: { type: "integer", minimum: 1, maximum: 100 } } },
    requires: [],
    handler: handleWorkflowTemplates
  }),
  defineTool({
    name: "workflow.read",
    description: "Read a saved workflow template.",
    risk: "low",
    parameters: { type: "object", properties: { name: { type: "string" } }, required: ["name"] },
    requires: [],
    handler: handleWorkflowRead
  }),
  defineTool({
    name: "workflow.save",
    description: "Save a workflow template.",
    risk: "medium",
    parameters: workflowSaveSchema,
    requires: [],
    handler: handleWorkflowSave
  }),
  defineTool({
    name: "workflow.delete",
    description: "Delete a saved workflow template.",
    risk: "medium",
    parameters: { type: "object", properties: { name: { type: "string" } }, required: ["name"] },
    requires: [],
    handler: handleWorkflowDelete
  }),
  defineTool({
    name: "workflow.validate",
    description: "Validate workflow nodes and edges.",
    risk: "low",
    parameters: workflowValidateSchema,
    requires: [],
    handler: handleWorkflowValidate
  }),
  defineTool({
    name: "workflow.run",
    description: "Run an inline workflow plan.",
    risk: "medium",
    parameters: workflowRunSchema,
    requires: ["store"],
    uses: ["taskRunner"],
    handler: handleWorkflowRun
  }),
  defineTool({
    name: "workflow.run_saved",
    description: "Run a saved workflow template.",
    risk: "medium",
    parameters: { type: "object", properties: { name: { type: "string" }, stop_on_error: { type: "boolean" } }, required: ["name"] },
    requires: ["store"],
    uses: ["taskRunner"],
    handler: handleWorkflowRunSaved
  })
];
