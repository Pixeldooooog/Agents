import { localExecutor } from "../execution/localExecutor.js";
import type { CommandExecutor, CommandExecution, CommandStatus, ExecutionPolicy } from "../ports/commandExecutor.js";
import { utf8Prefix } from "../execution/boundedOutput.js";

export type BackgroundCommand = {
  task_id: string;
  command: string;
  description: string;
  started_at: number;
  ended_at: number;
  readonly status: CommandStatus;
  readonly exit_code: number | null;
  execution: CommandExecution;
  done: Promise<void>;
};
const MAX_BACKGROUND_RECORDS = 128;
const backgroundCommands = new Map<string, BackgroundCommand>();

export function createBackgroundCommand(command: string, cwd: string, timeoutMs: number, description: string, signal?: AbortSignal, executor: CommandExecutor = localExecutor, policy: ExecutionPolicy = { mode: "local" }): BackgroundCommand {
  // Completed records are a bounded transient cache, never a durable task store.
  if (backgroundCommands.size >= MAX_BACKGROUND_RECORDS) {
    const completed = [...backgroundCommands.values()].find(record => record.ended_at > 0);
    if (!completed) throw new Error("background command capacity reached");
    backgroundCommands.delete(completed.task_id);
  }
  const execution = executor.start({ command, cwd, timeoutMs, signal, policy });
  const record: BackgroundCommand = {
    task_id: newShellTaskId(), command, description, started_at: Date.now() / 1000, ended_at: 0,
    get status() { return execution.status; },
    get exit_code() { return execution.exitCode; },
    execution, done: Promise.resolve()
  };
  record.done = execution.done.then(() => { record.ended_at = Date.now() / 1000; });
  backgroundCommands.set(record.task_id, record);
  return record;
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
    truncated: command.execution.stdout.truncated || command.execution.stderr.truncated
  };
}

export function backgroundOutput(
  command: BackgroundCommand,
  maxBytes: number
): { content: string; bytes: number; truncated: boolean } {
  const execution = command.execution;
  const content = `${execution.stdout.text()}${execution.stderr.text()}`;
  const bytes = execution.stdout.bytes + execution.stderr.bytes;
  const prefix = utf8Prefix(Buffer.from(content), maxBytes);
  return { content: prefix, bytes, truncated: execution.stdout.truncated || execution.stderr.truncated || Buffer.byteLength(content) > maxBytes };
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
