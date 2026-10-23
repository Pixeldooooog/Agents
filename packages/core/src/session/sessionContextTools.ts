import type { ToolDefinition } from "../tools/toolContracts.js";
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

export const sessionContextToolDefinitions: ToolDefinition[] = [
  {
    name: "session.status",
    description: "Read current session, workspace, model, enabled tool, and context-window status.",
    risk: "low",
    parameters: sessionStatusSchema,
    handler: handleSessionStatus
  },
  {
    name: "session.export",
    description: "Export current session messages to a workspace JSON or Markdown file.",
    risk: "medium",
    parameters: sessionExportSchema,
    handler: handleSessionExport
  },
  {
    name: "session.summary",
    description: "Summarize recent current-session messages for handoff or status review.",
    risk: "low",
    parameters: sessionSummarySchema,
    handler: handleSessionSummary
  },
  {
    name: "context.trace",
    description: "Read runtime events captured during the current run.",
    risk: "low",
    parameters: contextTraceSchema,
    handler: handleContextTrace
  },
  {
    name: "context.messages",
    description: "Read recent session message summaries.",
    risk: "low",
    parameters: sessionSummarySchema,
    handler: handleContextMessages
  },
  {
    name: "context.compact",
    description: "Compact older session messages into a summary placeholder.",
    risk: "medium",
    parameters: contextCompactSchema,
    handler: handleContextCompact
  },
  {
    name: "context.rewind",
    description: "Remove recent non-system messages from the current session context.",
    risk: "medium",
    parameters: contextRewindSchema,
    handler: handleContextRewind
  }
];
