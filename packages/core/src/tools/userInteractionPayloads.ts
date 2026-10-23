import { stat } from "node:fs/promises";
import path from "node:path";
import type { JsonObject } from "../types/jsonTypes.js";
import type { ToolExecutionContext } from "./toolContracts.js";
import { relativeWorkspacePath, resolveWorkspacePath } from "./toolInputs.js";

const imageExtensions = new Set([".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".svg"]);

export function askUserQuestion(args: JsonObject): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    questions: normalizeQuestions(args.questions),
    answers: stringRecord(args.answers)
  };
  if (args.annotations && typeof args.annotations === "object") payload.annotations = args.annotations;
  if (args.metadata && typeof args.metadata === "object") payload.metadata = args.metadata;
  return payload;
}

export async function sendUserMessage(context: ToolExecutionContext, args: JsonObject): Promise<Record<string, unknown>> {
  const status = String(args.status || "normal").trim();
  if (!["normal", "proactive"].includes(status)) throw new Error("status must be normal or proactive");
  const attachments = await resolveAttachments(context, Array.isArray(args.attachments) ? args.attachments : []);
  return {
    message: requiredText(args.message, "message"),
    status,
    sentAt: new Date().toISOString(),
    ...(attachments.length ? { attachments } : {})
  };
}

function normalizeQuestions(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) throw new Error("questions must be a list");
  if (value.length < 1 || value.length > 4) throw new Error("questions must include 1-4 items");
  const seenQuestions = new Set<string>();
  return value.map((item) => {
    if (!item || typeof item !== "object") throw new Error("question items must be objects");
    const payload = item as Record<string, unknown>;
    const question = requiredText(payload.question, "question");
    if (seenQuestions.has(question)) throw new Error("Question texts must be unique");
    seenQuestions.add(question);
    return {
      question,
      header: requiredText(payload.header, "header"),
      options: normalizeOptions(payload.options, question),
      multiSelect: Boolean(payload.multiSelect)
    };
  });
}

function normalizeOptions(value: unknown, question: string): Record<string, string>[] {
  if (!Array.isArray(value)) throw new Error("options must be a list");
  if (value.length < 2 || value.length > 4) throw new Error(`question ${question} must include 2-4 options`);
  const seenLabels = new Set<string>();
  return value.map((item) => {
    if (!item || typeof item !== "object") throw new Error("option items must be objects");
    const payload = item as Record<string, unknown>;
    const label = requiredText(payload.label, "option.label");
    if (seenLabels.has(label)) throw new Error("option labels must be unique within each question");
    seenLabels.add(label);
    return {
      label,
      description: requiredText(payload.description, "option.description"),
      ...(payload.preview ? { preview: String(payload.preview) } : {})
    };
  });
}

async function resolveAttachments(context: ToolExecutionContext, attachments: unknown[]): Promise<Record<string, unknown>[]> {
  const resolvedAttachments: Record<string, unknown>[] = [];
  for (const attachment of attachments) {
    const requestedPath = requiredText(attachment, "attachment");
    const absolutePath = resolveWorkspacePath(context.repoRoot, requestedPath);
    const info = await stat(absolutePath);
    if (!info.isFile()) throw new Error(`attachment must be a file: ${requestedPath}`);
    resolvedAttachments.push({
      path: relativeWorkspacePath(context.repoRoot, absolutePath),
      size: info.size,
      isImage: imageExtensions.has(path.extname(absolutePath).toLowerCase())
    });
  }
  return resolvedAttachments;
}

function requiredText(value: unknown, name: string): string {
  const text = String(value || "").trim();
  if (!text) throw new Error(`${name} is required`);
  return text;
}

function stringRecord(value: unknown): Record<string, string> {
  if (!value || typeof value !== "object") return {};
  return Object.fromEntries(Object.entries(value).map(([key, entryValue]) => [String(key), String(entryValue)]));
}
