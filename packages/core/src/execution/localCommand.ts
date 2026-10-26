import { spawn } from "node:child_process";
import type { CommandStatus } from "../ports/commandExecutor.js";
import { BoundedOutput } from "./boundedOutput.js";

export const COMMAND_TIMEOUT_MS = 30_000;
export const MAX_COMMAND_TIMEOUT_MS = 120_000;
export const COMMAND_STREAM_MAX_BYTES = 128 * 1024;
const TERMINATION_GRACE_MS = 200;

export type LocalCommand = {
  status: CommandStatus;
  exitCode: number | null;
  stdout: BoundedOutput;
  stderr: BoundedOutput;
  done: Promise<void>;
  stop(): void;
};

export function commandTimeoutMs(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value <= 0) return COMMAND_TIMEOUT_MS;
  return Math.min(value, MAX_COMMAND_TIMEOUT_MS);
}

/** Bounded host execution, NOT a filesystem/network/credential sandbox. */
export function startLocalCommand(command: string, cwd: string, timeoutMs: number, signal?: AbortSignal): LocalCommand {
  if (process.platform === "win32") throw new Error("local command process-group supervision is unsupported on Windows");
  const stdout = new BoundedOutput(COMMAND_STREAM_MAX_BYTES);
  const stderr = new BoundedOutput(COMMAND_STREAM_MAX_BYTES);
  let resolveDone!: () => void;
  const handle: LocalCommand = {
    status: "running", exitCode: null, stdout, stderr,
    done: new Promise(resolve => { resolveDone = resolve; }),
    stop: () => terminate("killed")
  };
  if (signal?.aborted) {
    handle.status = "killed";
    resolveDone();
    return handle;
  }
  const child = spawn(command, { cwd, shell: true, detached: true });
  let closed = false;
  let escalation: ReturnType<typeof setTimeout> | undefined;
  let finished = false;
  const timer = setTimeout(() => terminate("timed_out"), commandTimeoutMs(timeoutMs));
  const abort = () => terminate("killed");
  signal?.addEventListener("abort", abort, { once: true });
  // Cover cancellation occurring during spawn before listener registration.
  if (signal?.aborted) abort();

  function killGroup(kind: NodeJS.Signals): void {
    if (!child.pid) return;
    try { process.kill(-child.pid, kind); }
    catch (error) { if ((error as NodeJS.ErrnoException).code !== "ESRCH") stderr.append(`process-group signal failed: ${(error as Error).message}`); }
  }
  function finish(): void {
    if (finished) return;
    finished = true;
    clearTimeout(timer);
    signal?.removeEventListener("abort", abort);
    resolveDone();
  }
  function terminate(status: "killed" | "timed_out"): void {
    if (handle.status !== "running") return;
    handle.status = status;
    killGroup("SIGTERM");
    escalation = setTimeout(() => {
      killGroup("SIGKILL");
      escalation = undefined;
      // A descendant escaping the process group must not hold our pipes open forever.
      child.stdout.destroy();
      child.stderr.destroy();
      if (closed) finish();
    }, TERMINATION_GRACE_MS);
  }
  child.stdout.on("data", chunk => stdout.append(chunk));
  child.stderr.on("data", chunk => stderr.append(chunk));
  child.on("error", error => {
    handle.status = "error";
    stderr.append(error.message);
  });
  child.on("close", code => {
    closed = true;
    handle.exitCode = code;
    if (handle.status === "running") handle.status = code === 0 ? "completed" : "failed";
    // Also reap ordinary descendants that redirected their stdio and outlived the shell.
    if (!escalation) { killGroup("SIGKILL"); finish(); }
  });
  return handle;
}
