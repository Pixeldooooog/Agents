import type { AgentSpec } from "../types/agentTypes.js";
import type { ToolContext } from "../tools/toolContracts.js";

/** Worktree switches persist through spec metadata and the shared settings.repoRoot used by later calls. */
export type WorktreeToolContext = ToolContext<never, "settings">;
import type { WorktreeSession } from "./worktreeTypes.js";

export function activeSession(spec: AgentSpec | undefined): WorktreeSession | null {
  if (!spec?.metadata.active_worktree_session) return null;
  try {
    return JSON.parse(spec.metadata.active_worktree_session) as WorktreeSession;
  } catch {
    return null;
  }
}

export function setActiveSession(context: WorktreeToolContext, session: WorktreeSession): void {
  if (context.spec) context.spec.metadata.active_worktree_session = JSON.stringify(session);
}

export function clearActiveSession(context: WorktreeToolContext): void {
  if (context.spec) delete context.spec.metadata.active_worktree_session;
}

export function switchRepoRoot(context: WorktreeToolContext, repoRoot: string): void {
  context.repoRoot = repoRoot;
  if (context.settings) context.settings.repoRoot = repoRoot;
}
