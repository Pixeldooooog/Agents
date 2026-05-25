import type { OperationEvent, OperationFile, OperationPhase, OperationSceneKind, OperationSource, RunTraceResponse } from "../types";
import { operationFromFrame } from "./operationFrames";
import { fileHistoryOperation } from "./operationSpecialEvents";
import { createId } from "./sessionUtils";
import { fileTarget, isEditTool } from "./operationToolMapping";

type RuntimeEvent = {
  type?: string;
  name?: string;
  payload?: Record<string, any>;
};

export function projectRuntimeEvent(event: RuntimeEvent, runId = ""): OperationEvent[] {
  if (event.type === "operation_frame") return [operationFromFrame(event.payload || {}, runId)];
  if (event.type === "tool_start") return [operationFromToolEvent(event, "opening", runId)];
  if (event.type === "tool_result") return [operationFromToolEvent(event, event.payload?.is_error ? "error" : "done", runId)];
  if (event.type === "file_history_write") return [fileHistoryOperation(event, runId)];
  if (event.type === "web_search") return [genericOperation(event, "web", "web.search", "opening", runId)];
  if (event.type === "browser_action") return [genericOperation(event, "browser", "browser.action", "opening", runId)];
  if (event.type === "code_start") return [genericOperation(event, "terminal", "code.run", "opening", runId)];
  if (event.type === "done") {
    return [{
      id: `summary:${createId()}`,
      runId,
      toolCallId: "",
      toolName: "assistant.done",
      scene: "summary",
      phase: event.payload?.error ? "error" : "done",
      title: event.payload?.error ? "Run ended with an error" : "Run complete",
      detail: event.payload?.error || "Windows closed. Result returned to chat.",
      resultPreview: event.payload
    }];
  }
  return [];
}

export function projectRunTrace(trace: RunTraceResponse, fallbackRunId = ""): OperationEvent[] {
  const runId = trace.run_id || fallbackRunId;
  const snapshots = Array.isArray(trace.sandbox_snapshots) ? trace.sandbox_snapshots : [];
  const artifacts = Array.isArray(trace.artifacts) ? trace.artifacts : [];
  const frameEvents = Array.isArray(trace.operation_frames) ? trace.operation_frames.map((frame) => operationFromFrame(frame, runId)) : [];
  const events: OperationEvent[] = [...frameEvents];
  const latestSnapshot = snapshots[snapshots.length - 1];
  if (latestSnapshot) {
    events.push({
      id: `trace:snapshot:${latestSnapshot.snapshot_id || snapshots.length}`,
      runId,
      toolCallId: "",
      toolName: "workspace.snapshot",
      scene: "workspace",
      phase: "done",
      title: "Workspace snapshot captured",
      target: latestSnapshot.phase || "workspace",
      detail: `${latestSnapshot.file_count || 0} files · ${formatBytes(latestSnapshot.total_bytes || 0)}`,
      resultPreview: latestSnapshot.manifest,
      diffPreview: latestSnapshot.diff,
      artifacts,
      files: filesFromManifest(latestSnapshot.manifest),
      stats: { file_count: latestSnapshot.file_count || 0, total_bytes: latestSnapshot.total_bytes || 0 },
      endedAt: Date.now(),
    });
  }
  if (artifacts.length) {
    events.push({
      id: `trace:artifacts:${runId}:${artifacts.length}`,
      runId,
      toolCallId: "",
      toolName: "artifacts.collect",
      scene: "summary",
      phase: "done",
      title: "Artifacts collected",
      target: `${artifacts.length} artifact${artifacts.length > 1 ? "s" : ""}`,
      detail: "Run outputs are available in trace.",
      artifacts,
      endedAt: Date.now(),
    });
  }
  return events;
}

function operationFromToolEvent(event: RuntimeEvent, phase: OperationPhase, fallbackRunId: string): OperationEvent {
  const payload = event.payload || {};
  const call = payload.tool_call || payload;
  const toolName = call.name || payload.name || event.name || "tool";
  const args = call.arguments || payload.arguments || {};
  const result = payload.raw || payload.result || payload.content || payload;
  return {
    id: `${call.id || payload.tool_call_id || toolName}:${phase}:${createId()}`,
    runId: payload.run_id || fallbackRunId,
    toolCallId: call.id || payload.tool_call_id || "",
    toolName,
    scene: sceneForTool(toolName),
    phase,
    title: titleForTool(toolName, phase),
    target: targetForTool(toolName, args, result),
    detail: detailForTool(toolName, args, result),
    argsPreview: scrubArgs(args),
    resultPreview: previewResult(result),
    diffPreview: diffFromResult(result),
    artifacts: artifactsFromResult(result),
    sources: sourcesFromResult(result),
    files: filesFromResult(toolName, args, result),
    stats: statsFromResult(result),
    startedAt: phase === "opening" ? Date.now() : undefined,
    endedAt: phase === "done" || phase === "error" ? Date.now() : undefined
  };
}

function genericOperation(event: RuntimeEvent, scene: OperationSceneKind, toolName: string, phase: OperationPhase, runId: string): OperationEvent {
  const payload = event.payload || {};
  return {
    id: `${toolName}:${phase}:${createId()}`,
    runId: payload.run_id || runId,
    toolCallId: "",
    toolName: event.name || toolName,
    scene,
    phase,
    title: titleForTool(event.name || toolName, phase),
    target: targetForTool(event.name || toolName, payload, payload),
    detail: detailForTool(event.name || toolName, payload, payload),
    argsPreview: scrubArgs(payload),
    sources: sourcesFromResult(payload),
    startedAt: Date.now(),
  };
}

export function sceneForTool(toolName: string): OperationSceneKind {
  if (isEditTool(toolName)) return "edit";
  if (toolName.startsWith("web.")) return "web";
  if (toolName.startsWith("browser.")) return "browser";
  if (toolName.startsWith("shell.") || toolName.startsWith("test.")) return "terminal";
  if (toolName.startsWith("git.")) return "git";
  if (toolName.startsWith("skill.") || toolName.startsWith("prompt.") || toolName.startsWith("mcp.") || toolName.startsWith("context.")) return "document";
  if (toolName.startsWith("todo.") || toolName.startsWith("plan.") || toolName.startsWith("task.") || toolName.startsWith("schedule.")) return "document";
  if (toolName.startsWith("workflow.") || toolName.startsWith("agent.") || toolName.startsWith("team.")) return "document";
  return "workspace";
}

function titleForTool(toolName: string, phase: OperationPhase) {
  const verb = phase === "done" ? "Completed" : phase === "error" ? "Failed" : "Opening";
  if (toolName.startsWith("web.")) return `${verb} web search`;
  if (toolName.startsWith("browser.")) return `${verb} browser`;
  if (toolName.startsWith("shell.") || toolName.startsWith("test.")) return `${verb} terminal`;
  if (toolName.startsWith("git.")) return `${verb} git operation`;
  if (toolName.startsWith("skill.")) return `${verb} skill context`;
  if (toolName.startsWith("mcp.") || toolName.startsWith("prompt.") || toolName.startsWith("context.")) return `${verb} document context`;
  if (toolName.startsWith("todo.") || toolName.startsWith("plan.")) return `${verb} planning context`;
  if (toolName.startsWith("task.") || toolName.startsWith("schedule.")) return `${verb} task context`;
  if (toolName.startsWith("workflow.") || toolName.startsWith("agent.") || toolName.startsWith("team.")) return `${verb} orchestration context`;
  if (isEditTool(toolName)) return `${verb} workspace edit`;
  return `${verb} workspace file`;
}

function targetForTool(toolName: string, args: Record<string, any>, result: any) {
  const path = fileTarget(args);
  if (path) return String(path);
  if (args.source_path || args.destination_path) return [args.source_path, args.destination_path].filter(Boolean).join(" -> ");
  if (args.query) return String(args.query);
  if (args.url) return String(args.url);
  if (Array.isArray(args.urls)) return args.urls.slice(0, 2).join(", ");
  if (args.command) return String(args.command);
  if (args.name) return String(args.name);
  if (args.title) return String(args.title);
  if (args.task_id) return String(args.task_id);
  if (args.agent_id) return String(args.agent_id);
  if (args.team_id) return String(args.team_id);
  return typeof result?.path === "string" ? result.path
    : typeof result?.notebook_path === "string" ? result.notebook_path
    : typeof result?.filePath === "string" ? result.filePath
    : toolName;
}

function detailForTool(toolName: string, args: Record<string, any>, result: any) {
  if (toolName.startsWith("web.")) return args.query ? `Searching for "${args.query}"` : "Inspecting web sources";
  if (toolName.startsWith("shell.") || toolName.startsWith("test.")) return args.command || "Running command";
  if (toolName.startsWith("git.")) return args.path || args.paths?.join(", ") || "Inspecting repository state";
  if (toolName.startsWith("skill.")) return args.name ? `Opening ${args.name}` : "Opening skill context";
  if (toolName.startsWith("task.")) return args.title || args.task_id || "Updating task state";
  if (toolName.startsWith("workflow.")) return args.name || args.workflow_id || "Inspecting workflow";
  if (toolName.startsWith("agent.") || toolName.startsWith("team.")) return args.prompt || args.message || "Coordinating agent work";
  if (result?.is_error) return "Tool returned an error";
  return targetForTool(toolName, args, result);
}

function scrubArgs(args: Record<string, any>) {
  const clone = { ...args };
  for (const key of Object.keys(clone)) if (/key|token|secret|password/i.test(key)) clone[key] = "[redacted]";
  return clone;
}

function previewResult(result: any) {
  if (result == null) return undefined;
  if (typeof result === "string") return result.slice(0, 1200);
  return result;
}

function sourcesFromResult(result: any): OperationSource[] {
  const sources = Array.isArray(result?.sources) ? result.sources : [];
  return sources.slice(0, 6).map((source: any) => ({
    title: String(source.title || source.url || "Source"),
    url: String(source.url || ""),
    domain: source.domain ? String(source.domain) : domainFromUrl(source.url),
    content: source.content ? String(source.content).slice(0, 220) : "",
    score: typeof source.score === "number" ? source.score : undefined,
  }));
}

function filesFromResult(toolName: string, args: Record<string, any>, result: any): OperationFile[] {
  const entries = Array.isArray(result?.entries) ? result.entries : fileEntries(result?.files);
  const files = entries.slice(0, 12).map((entry: any) => ({
    path: String(entry.path || entry.name || entry),
    kind: String(entry.kind || entry.type || ""),
    status: String(entry.status || ""),
  }));
  const targetPath = fileTarget(args);
  if (!files.length && targetPath) files.push({ path: String(targetPath), kind: isEditTool(toolName) ? "file" : "" });
  return files;
}

function filesFromManifest(manifest: any): OperationFile[] {
  const entries = fileEntries(manifest?.files || manifest);
  return entries.slice(0, 12).map((entry: any) => ({ path: String(entry.path || entry), kind: String(entry.kind || "") }));
}

function fileEntries(value: any): any[] {
  if (Array.isArray(value)) return value;
  if (value && typeof value === "object") return Object.values(value);
  return [];
}

function statsFromResult(result: any) {
  const meta = result?._meta;
  if (!meta || typeof meta !== "object") return undefined;
  return { duration_ms: meta.duration_ms, sandbox: meta.sandbox };
}

function diffFromResult(result: any) {
  return result?.diff || result?._meta?.sandbox?.diff || undefined;
}

function artifactsFromResult(result: any) {
  if (Array.isArray(result?.artifacts)) return result.artifacts;
  return result?.artifact ? [result.artifact] : [];
}

function domainFromUrl(url: string) {
  try {
    return new URL(String(url)).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}
