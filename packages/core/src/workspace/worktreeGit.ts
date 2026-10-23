import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import type { WorktreeChanges, WorktreeSession } from "./worktreeTypes.js";

export async function gitRoot(cwd: string): Promise<string> {
  const result = await git(cwd, ["rev-parse", "--show-toplevel"], 30, false);
  if (result.exitCode !== 0) {
    throw new Error("Cannot create a worktree: current workspace is not in a git repository.");
  }
  return result.stdout.trim();
}

export async function isGitWorktree(worktreePath: string): Promise<boolean> {
  if (!existsSync(worktreePath)) return false;
  const result = await git(worktreePath, ["rev-parse", "--is-inside-work-tree"], 30, false);
  return result.exitCode === 0 && result.stdout.trim() === "true";
}

export async function preparePrRef(repoRoot: string, prNumber: number): Promise<string> {
  await git(repoRoot, ["fetch", "origin", `pull/${prNumber}/head`], 60);
  return "FETCH_HEAD";
}

export async function countWorktreeChanges(session: WorktreeSession): Promise<WorktreeChanges> {
  const status = await git(session.worktreePath, ["status", "--porcelain", "--untracked-files=all"], 30, false);
  const changedFiles = status.exitCode === 0
    ? status.stdout.split(/\r?\n/).filter((line) => line.trim()).length
    : 0;
  const revList = await git(session.worktreePath, ["rev-list", "--count", `${session.originalHeadCommit}..HEAD`], 30, false);
  return { changedFiles, commits: revList.exitCode === 0 ? Number(revList.stdout.trim() || 0) : 0 };
}

export function git(
  cwd: string,
  args: string[],
  timeoutSeconds = 30,
  check = true
): Promise<{ exitCode: number | null; stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const child = spawn("git", args, {
      cwd,
      env: { ...process.env, GIT_TERMINAL_PROMPT: "0", GIT_ASKPASS: "" }
    });
    const stdout: Buffer[] = [];
    const stderr: Buffer[] = [];
    const timer = setTimeout(() => child.kill("SIGTERM"), timeoutSeconds * 1000);
    child.stdout.on("data", (chunk) => stdout.push(Buffer.from(chunk)));
    child.stderr.on("data", (chunk) => stderr.push(Buffer.from(chunk)));
    child.on("error", reject);
    child.on("close", (exitCode) => {
      clearTimeout(timer);
      const result = {
        exitCode,
        stdout: Buffer.concat(stdout).toString("utf8"),
        stderr: Buffer.concat(stderr).toString("utf8")
      };
      if (check && exitCode !== 0) {
        const errorDetail = (result.stderr || result.stdout || `exit code ${exitCode}`).trim();
        reject(new Error(`Git command failed: ${errorDetail}`));
      } else {
        resolve(result);
      }
    });
  });
}
