import type { OperationPhase, OperationSceneKind } from "../types/runtimeTypes";
import { fileTarget, isEditTool } from "./operationToolMapping";

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

export function titleForTool(toolName: string, phase: OperationPhase) {
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

export function targetForTool(toolName: string, args: Record<string, any>, result: any) {
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

export function detailForTool(toolName: string, args: Record<string, any>, result: any) {
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
