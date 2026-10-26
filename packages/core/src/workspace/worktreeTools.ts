import { mkdir } from "node:fs/promises";
import path from "node:path";
import type { JsonObject } from "../types/jsonTypes.js";
import type { ToolDefinition, ToolExecutionContext } from "../tools/toolContracts.js";
import { booleanArg, numberArg, stringArg } from "../tools/toolInputs.js";
import { countWorktreeChanges, git, gitRoot, isGitWorktree, preparePrRef } from "./worktreeGit.js";
import { flattenSlug, worktreeRequest } from "./worktreeNaming.js";
import { activeSession, clearActiveSession, setActiveSession, switchRepoRoot } from "./worktreeSession.js";
import { worktreeEnterSchema, worktreeExitSchema } from "./worktreeSchemas.js";
import type { WorktreeSession } from "./worktreeTypes.js";

const noActiveWorktreeSessionMessage = [
  "No-op: there is no active worktree session to exit.",
  "This tool only operates on worktrees created by worktree.enter in the current session.",
  "No filesystem changes were made."
].join(" ");

export const worktreeToolDefinitions: ToolDefinition[] = [
  {
    name: "worktree.enter",
    description: "Create or resume an isolated git worktree and switch the session workspace to it.",
    risk: "medium",
    parameters: worktreeEnterSchema,
    handler: enterWorktree
  },
  {
    name: "worktree.exit",
    description: "Exit the active git worktree, preserving or removing it after safety checks.",
    risk: "medium",
    parameters: worktreeExitSchema,
    handler: exitWorktree
  }
];

async function enterWorktree(context: ToolExecutionContext, args: JsonObject) {
  const currentSession = activeSession(context.spec);
  if (currentSession) throw new Error(`Already in a worktree session at ${currentSession.worktreePath || "unknown"}`);
  const requested = worktreeRequest(stringArg(args.name), numberArg(args.pr_number, 0));
  const repoRoot = await gitRoot(context.repoRoot);
  const worktreePath = path.join(repoRoot, ".kevin", "worktrees", flattenSlug(requested.slug));
  const branch = `worktree-${flattenSlug(requested.slug)}`;
  await mkdir(path.dirname(worktreePath), { recursive: true });
  const existed = await isGitWorktree(worktreePath);
  const baseRef = requested.prNumber ? await preparePrRef(repoRoot, requested.prNumber) : "HEAD";
  if (!existed) await git(repoRoot, ["worktree", "add", "-B", branch, worktreePath, baseRef], 60);
  const headCommit = (await git(worktreePath, ["rev-parse", "HEAD"])).stdout.trim();
  const session: WorktreeSession = {
    originalCwd: repoRoot,
    worktreePath,
    worktreeName: requested.slug,
    worktreeBranch: branch,
    originalHeadCommit: headCommit,
    sessionId: context.runId || crypto.randomUUID(),
    prNumber: requested.prNumber
  };
  setActiveSession(context, session);
  switchRepoRoot(context, worktreePath);
  return {
    worktreePath,
    worktreeBranch: branch,
    resumed: existed,
    copiedFiles: [],
    copiedLocalFiles: [],
    symlinkedDirectories: [],
    hooksPath: "",
    usedSparsePaths: false,
    prNumber: requested.prNumber,
    baseRef,
    headCommit,
    tmuxSessionName: "",
    tmuxCreated: false,
    tmuxError: "",
    message: `${existed ? "Resumed" : "Created"} worktree at ${worktreePath} on branch ${branch}. Session is now using that worktree.`
  };
}

async function exitWorktree(context: ToolExecutionContext, args: JsonObject) {
  const action = stringArg(args.action);
  if (!["keep", "remove"].includes(action)) throw new Error("action must be keep or remove");
  const session = activeSession(context.spec);
  if (!session) {
    return {
      action,
      noop: true,
      reason: "no_active_worktree_session",
      originalCwd: context.repoRoot,
      worktreePath: "",
      worktreeBranch: "",
      message: noActiveWorktreeSessionMessage
    };
  }
  const changes = await countWorktreeChanges(session);
  if (action === "remove" && !booleanArg(args.discard_changes) && (changes.changedFiles || changes.commits)) {
    const parts = [];
    if (changes.changedFiles) parts.push(`${changes.changedFiles} changed file(s)`);
    if (changes.commits) parts.push(`${changes.commits} commit(s)`);
    throw new Error(`Worktree contains ${parts.join(" and ")}. Re-run with discard_changes=true to remove it.`);
  }
  clearActiveSession(context);
  switchRepoRoot(context, session.originalCwd);
  if (action === "keep") {
    return {
      action: "keep",
      originalCwd: session.originalCwd,
      worktreePath: session.worktreePath,
      worktreeBranch: session.worktreeBranch,
      message: `Exited worktree. Your work is preserved at ${session.worktreePath} on branch ${session.worktreeBranch}. Session is now back in ${session.originalCwd}.`
    };
  }
  await git(session.originalCwd, ["worktree", "remove", "--force", session.worktreePath], 60);
  const branchDelete = await git(session.originalCwd, ["branch", "-D", session.worktreeBranch], 30, false);
  const branchDeleteDetail = branchDelete.exitCode ? ` ${branchDelete.stderr || branchDelete.stdout}` : "";
  return {
    action: "remove",
    originalCwd: session.originalCwd,
    worktreePath: session.worktreePath,
    worktreeBranch: session.worktreeBranch,
    discardedFiles: changes.changedFiles,
    discardedCommits: changes.commits,
    tmuxSessionName: "",
    tmuxTerminated: false,
    tmuxError: "",
    message: `Exited and removed worktree at ${session.worktreePath}. Session is now back in ${session.originalCwd}.${branchDeleteDetail}`
  };
}
