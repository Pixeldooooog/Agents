export type WorktreeSession = {
  originalCwd: string;
  worktreePath: string;
  worktreeName: string;
  worktreeBranch: string;
  originalHeadCommit: string;
  sessionId: string;
  prNumber: number | null;
};

export type WorktreeRequest = {
  slug: string;
  prNumber: number | null;
};

export type WorktreeChanges = {
  changedFiles: number;
  commits: number;
};
