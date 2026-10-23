import { spawn } from "node:child_process";

export type BackgroundCommand = {
  task_id: string;
  command: string;
  description: string;
  started_at: number;
  ended_at: number;
  status: "running" | "completed" | "failed" | "killed" | "timed_out" | "error";
  exit_code: number | null;
  stdout: Buffer[];
  stderr: Buffer[];
  child: ReturnType<typeof spawn>;
  done: Promise<void>;
};

const backgroundCommands = new Map<string, BackgroundCommand>();

export function createBackgroundCommand(command: string, cwd: string, timeoutMs: number, description: string): BackgroundCommand {
  const child = spawn(command, { cwd, shell: true });
  const taskId = newShellTaskId();
  const backgroundCommand: BackgroundCommand = {
    task_id: taskId,
    command,
    description,
    started_at: Date.now() / 1000,
    ended_at: 0,
    status: "running",
    exit_code: null,
    stdout: [],
    stderr: [],
    child,
    done: Promise.resolve()
  };
  const timer = setTimeout(() => {
    if (backgroundCommand.status === "running") {
      backgroundCommand.status = "timed_out";
      child.kill("SIGTERM");
    }
  }, timeoutMs);
  backgroundCommand.done = new Promise((resolve) => {
    child.stdout.on("data", (chunk) => backgroundCommand.stdout.push(Buffer.from(chunk)));
    child.stderr.on("data", (chunk) => backgroundCommand.stderr.push(Buffer.from(chunk)));
    child.on("error", (error) => {
      backgroundCommand.status = "error";
      backgroundCommand.stderr.push(Buffer.from(error.message));
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      backgroundCommand.exit_code = code;
      if (backgroundCommand.status === "running") backgroundCommand.status = code === 0 ? "completed" : "failed";
      backgroundCommand.ended_at = Date.now() / 1000;
      resolve();
    });
  });
  backgroundCommands.set(taskId, backgroundCommand);
  return backgroundCommand;
}

export function listBackgroundCommands(): BackgroundCommand[] {
  return [...backgroundCommands.values()];
}

export function resolveBackgroundCommand(taskId: unknown): BackgroundCommand {
  const target = String(taskId || "").trim();
  if (!target) throw new Error("task_id is required");
  const matches = listBackgroundCommands().filter((command) => {
    return command.task_id === target || command.task_id.startsWith(target);
  });
  if (!matches.length) throw new Error(`background shell task not found: ${target}`);
  if (matches.length > 1) throw new Error(`ambiguous background shell task id: ${target}`);
  return matches[0];
}

export function backgroundPayload(command: BackgroundCommand): Record<string, unknown> {
  return {
    task_id: command.task_id,
    command: command.command,
    description: command.description,
    status: command.status,
    started_at: command.started_at,
    ended_at: command.ended_at,
    exit_code: command.exit_code,
    output_path: `.agents/task-output/${command.task_id}.log`
  };
}

export function backgroundOutput(
  command: BackgroundCommand,
  maxBytes: number
): { content: string; bytes: number; truncated: boolean } {
  const content = `${Buffer.concat(command.stdout).toString("utf8")}${Buffer.concat(command.stderr).toString("utf8")}`;
  const bytes = Buffer.byteLength(content);
  return { content: content.slice(0, maxBytes), bytes, truncated: bytes > maxBytes };
}

export function waitWithTimeout(promise: Promise<void>, timeoutMs: number): Promise<void> {
  if (timeoutMs <= 0) return Promise.resolve();
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, timeoutMs);
    promise.finally(() => {
      clearTimeout(timer);
      resolve();
    });
  });
}

function newShellTaskId(): string {
  let taskId = "";
  do {
    taskId = `shell_${crypto.randomUUID().replaceAll("-", "").slice(0, 12)}`;
  } while (backgroundCommands.has(taskId));
  return taskId;
}
