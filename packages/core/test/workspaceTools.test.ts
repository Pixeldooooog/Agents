import { describe, expect, test } from "bun:test";
import { mkdtemp, readFile, realpath, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { executeBuiltinTool, loadSettings, specFromPayload } from "../src/index.js";

describe("workspace editing and navigation tools", () => {
  test("edits a Jupyter notebook cell", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "agents-notebook-tools-"));
    try {
      await writeFile(path.join(root, "notebook.ipynb"), JSON.stringify({
        nbformat: 4,
        nbformat_minor: 5,
        metadata: { language_info: { name: "python" } },
        cells: [{ cell_type: "code", id: "cell-a", source: "print('old')", metadata: {}, execution_count: 1, outputs: [{}] }]
      }));

      const edited = await executeBuiltinTool(root, "notebook.edit", {
        notebook_path: "notebook.ipynb",
        cell_id: "cell-a",
        new_source: "print('new')"
      });
      expect(JSON.parse(edited.result.content).cell_id).toBe("cell-a");
      const notebook = JSON.parse(await readFile(path.join(root, "notebook.ipynb"), "utf8"));
      expect(notebook.cells[0].source).toBe("print('new')");
      expect(notebook.cells[0].outputs).toEqual([]);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("queries an injected LSP provider", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "agents-lsp-tools-"));
    try {
      await writeFile(path.join(root, "src.ts"), "export const target = 1;\n");
      const queried = await executeBuiltinTool(root, "lsp.query", {
        operation: "hover",
        filePath: "src.ts",
        line: 1,
        character: 14
      }, {
        lspProvider: {
          query: async (request) => ({ operation: request.operation, filePath: request.filePath, result: "const target: 1", resultCount: 1 })
        }
      });
      const payload = JSON.parse(queried.result.content);
      expect(payload.result).toContain("target");
      expect(payload.resultCount).toBe(1);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("enters and removes a git worktree session", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "agents-worktree-tools-"));
    try {
      runGit(root, ["init"]);
      runGit(root, ["config", "user.email", "test@example.com"]);
      runGit(root, ["config", "user.name", "Test User"]);
      await writeFile(path.join(root, "README.md"), "hello\n");
      runGit(root, ["add", "README.md"]);
      runGit(root, ["commit", "-m", "initial"]);

      const settings = await loadSettings(root);
      const spec = specFromPayload({ message: "worktree" });
      const entered = await executeBuiltinTool(root, "worktree.enter", { name: "spike" }, { settings, spec });
      const enteredPayload = JSON.parse(entered.result.content);
      expect(enteredPayload.worktreeBranch).toBe("worktree-spike");
      expect(settings.repoRoot).toBe(enteredPayload.worktreePath);

      const exited = await executeBuiltinTool(settings.repoRoot, "worktree.exit", { action: "remove", discard_changes: true }, { settings, spec });
      expect(JSON.parse(exited.result.content).action).toBe("remove");
      expect(await realpath(settings.repoRoot)).toBe(await realpath(root));
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });
});

function runGit(cwd: string, args: string[]): void {
  const result = spawnSync("git", args, { cwd, encoding: "utf8" });
  if (result.status !== 0) throw new Error(result.stderr || result.stdout || `git ${args.join(" ")} failed`);
}
