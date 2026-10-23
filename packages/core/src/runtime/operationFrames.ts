import type { RuntimeEvent } from "../types/runtimeTypes.js";

export type OperationFrame = {
  id: string;
  runId: string;
  toolCallId?: string;
  toolName: string;
  scene: string;
  phase: "opening" | "running" | "closing" | "done" | "error";
  title: string;
  detail?: string;
  argsPreview?: Record<string, unknown>;
  resultPreview?: unknown;
  sequence: number;
  source: string;
};

export function buildOperationFrames(runId: string, events: RuntimeEvent[] = []): OperationFrame[] {
  const frames: OperationFrame[] = [];
  let sequence = 0;
  for (const event of events) {
    const payload = event.payload || {};
    if (event.type === "tool_start") {
      frames.push(frame(runId, event, payload, sequence++, "opening"));
      frames.push(frame(runId, event, payload, sequence++, "running"));
    }
    if (event.type === "tool_result") {
      frames.push(frame(runId, event, payload, sequence++, payload.is_error ? "error" : "closing"));
      frames.push(frame(runId, event, payload, sequence++, payload.is_error ? "error" : "done"));
    }
  }
  return frames;
}

function frame(runId: string, event: RuntimeEvent, payload: Record<string, unknown>, sequence: number, phase: OperationFrame["phase"]): OperationFrame {
  const toolName = String(payload.name || event.name || "workspace");
  const toolCallId = String(payload.tool_call_id || payload.id || toolName);
  return {
    id: `operation:${toolCallId}:${sequence}:${phase}`,
    runId,
    toolCallId,
    toolName,
    scene: sceneFor(toolName),
    phase,
    title: titleFor(toolName, phase),
    detail: phase === "running" ? "Execute tool" : "Capture tool state",
    argsPreview: objectField(payload.arguments),
    resultPreview: payload.content,
    sequence,
    source: "runtime_trace"
  };
}

function sceneFor(toolName: string): string {
  if (toolName.startsWith("filesystem.")) return "edit";
  if (toolName.startsWith("web.")) return "web";
  if (toolName.startsWith("shell.") || toolName.startsWith("test.")) return "terminal";
  if (toolName.startsWith("git.")) return "git";
  return "workspace";
}

function titleFor(toolName: string, phase: string): string {
  const action = phase === "done" ? "Completed" : phase === "error" ? "Failed" : phase === "running" ? "Operating" : "Opening";
  return `${action} ${toolName}`;
}

function objectField(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : undefined;
}
