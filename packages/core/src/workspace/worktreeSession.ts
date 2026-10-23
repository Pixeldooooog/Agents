import type { AgentSpec } from "../types/agentTypes.js";
import type { ToolExecutionContext } from "../tools/toolContracts.js";
import type { WorktreeSession } from "./worktreeTypes.js";

export function activeSession(spec: AgentSpec | undefined): WorktreeSession | null {
  if (!spec?.metadata.active_worktree_session) return null;
  try {
    return JSON.parse(spec.metadata.active_worktree_session) as WorktreeSession;
  } catch {
    return null;
  }
}

export function setActiveSession(context: ToolExecutionContext, session: WorktreeSession): void {
  context.activeWorktreeSession = session;
  if (context.spec) context.spec.metadata.active_worktree_session = JSON.stringify(session);
}

export function clearActiveSession(context: ToolExecutionContext): void {
  context.activeWorktreeSession = {};
  if (context.spec) delete context.spec.metadata.active_worktree_session;
}

export function switchRepoRoot(context: ToolExecutionContext, repoRoot: string): void {
  context.repoRoot = repoRoot;
  if (context.settings) context.settings.repoRoot = repoRoot;
}
