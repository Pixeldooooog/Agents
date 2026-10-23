import path from "node:path";
import type { Message } from "../types/runtimeTypes.js";
import type { ToolExecutionContext } from "../tools/toolContracts.js";
import { resolveWorkspacePath } from "../tools/toolInputs.js";
import { workspacePayload } from "./sessionContextPayloads.js";

export type SessionExportFormat = "json" | "markdown";

export function jsonExport(context: ToolExecutionContext, messages: Message[]): string {
  return `${JSON.stringify({
    exported_at: Date.now() / 1000,
    workspace: workspacePayload(context),
    model: { protocol: context.spec?.protocol || "", model: context.spec?.model || "" },
    messages
  }, null, 2)}\n`;
}

export function markdownExport(context: ToolExecutionContext, messages: Message[]): string {
  const lines = [
    "# Session Export",
    "",
    `- Model: ${context.spec?.protocol || "-"} / ${context.spec?.model || "-"}`,
    `- Workspace: ${context.repoRoot}`,
    `- Messages: ${messages.length}`,
    ""
  ];
  for (const message of messages) lines.push(`## ${message.role}`, "", message.content, "");
  return `${lines.join("\n").trimEnd()}\n`;
}

export function exportFormat(value: unknown): SessionExportFormat {
  const format = String(value || "json").trim().toLowerCase();
  if (format === "md" || format === "markdown") return "markdown";
  if (format === "json") return "json";
  throw new Error("format must be json or markdown");
}

export function exportPath(repoRoot: string, requestedPath: string, format: SessionExportFormat): string {
  const suffix = format === "markdown" ? "md" : "json";
  const defaultPath = `.agents/exports/session-${timestampLabel()}.${suffix}`;
  const target = String(requestedPath || defaultPath).trim();
  if (!target || target.endsWith("/") || target.endsWith("\\")) {
    throw new Error("export path must include a file name");
  }
  return resolveWorkspacePath(repoRoot, target);
}

function timestampLabel(): string {
  return new Date().toISOString().replace(/[-:TZ.]/g, "").slice(0, 14);
}
