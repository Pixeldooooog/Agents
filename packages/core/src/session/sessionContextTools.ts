import { defineTool, type RegisteredTool } from "../tools/toolContracts.js";
import {
  handleContextCompact,
  handleContextMessages,
  handleContextRewind,
  handleContextTrace,
  handleSessionExport,
  handleSessionStatus,
  handleSessionSummary
} from "./sessionContextToolHandlers.js";
import {
  contextCompactSchema,
  contextRewindSchema,
  contextTraceSchema,
  sessionExportSchema,
  sessionStatusSchema,
  sessionSummarySchema
} from "./sessionContextToolSchemas.js";

export const sessionContextToolDefinitions: RegisteredTool[] = [
  defineTool({
    name: "session.status",
    description: "Read current session, workspace, model, enabled tool, and context-window status.",
    risk: "low",
    parameters: sessionStatusSchema,
    requires: [],
    uses: ["conversation", "store"],
    handler: handleSessionStatus
  }),
  defineTool({
    name: "session.export",
    description: "Export current session messages to a workspace JSON or Markdown file.",
    risk: "medium",
    parameters: sessionExportSchema,
    requires: [],
    uses: ["conversation"],
    handler: handleSessionExport
  }),
  defineTool({
    name: "session.summary",
    description: "Summarize recent current-session messages for handoff or status review.",
    risk: "low",
    parameters: sessionSummarySchema,
    requires: [],
    uses: ["conversation"],
    handler: handleSessionSummary
  }),
  defineTool({
    name: "context.trace",
    description: "Read runtime events captured during the current run.",
    risk: "low",
    parameters: contextTraceSchema,
    requires: [],
    uses: ["conversation"],
    handler: handleContextTrace
  }),
  defineTool({
    name: "context.messages",
    description: "Read recent session message summaries.",
    risk: "low",
    parameters: sessionSummarySchema,
    requires: [],
    uses: ["conversation"],
    handler: handleContextMessages
  }),
  defineTool({
    name: "context.compact",
    description: "Compact older session messages into a summary placeholder.",
    risk: "medium",
    parameters: contextCompactSchema,
    requires: ["conversation"],
    handler: handleContextCompact
  }),
  defineTool({
    name: "context.rewind",
    description: "Remove recent non-system messages from the current session context.",
    risk: "medium",
    parameters: contextRewindSchema,
    requires: ["conversation"],
    handler: handleContextRewind
  })
];
