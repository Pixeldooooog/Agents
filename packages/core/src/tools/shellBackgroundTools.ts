import type { JsonObject } from "../types/jsonTypes.js";
import type { ToolExecutionContext } from "./toolContracts.js";
import { numberArg } from "./toolInputs.js";
import {
  backgroundOutput,
  backgroundPayload,
  createBackgroundCommand,
  listBackgroundCommands,
  resolveBackgroundCommand,
  waitWithTimeout
} from "./shellBackgroundRecords.js";

export function startBackgroundCommand(
  command: string,
  cwd: string,
  timeoutMs: number,
  description: string
): Record<string, unknown> {
  const backgroundCommand = createBackgroundCommand(command, cwd, timeoutMs, description);
  return {
    ...backgroundPayload(backgroundCommand),
    backgroundTaskId: backgroundCommand.task_id,
    backgroundedByUser: true,
    assistantAutoBackgrounded: false,
    stdout: "",
    stderr: "",
    exit_code: 0
  };
}

export async function shellOutput(_context: ToolExecutionContext, args: JsonObject) {
  const command = resolveBackgroundCommand(args.task_id);
  if (args.block !== false && command.status === "running") {
    await waitWithTimeout(command.done, Math.max(0, numberArg(args.timeout_seconds, 30)) * 1000);
  }
  const maxBytes = Math.max(1, Math.min(200000, numberArg(args.max_bytes, 20000)));
  const output = backgroundOutput(command, maxBytes);
  return {
    retrieval_status: command.status === "running" ? "not_ready" : "success",
    task: backgroundPayload(command),
    output: output.content,
    bytes: output.bytes,
    truncated: output.truncated
  };
}

export async function shellBackgrounds() {
  const backgroundCommands = listBackgroundCommands();
  return { background_commands: backgroundCommands.map(backgroundPayload), count: backgroundCommands.length };
}

export async function shellKill(_context: ToolExecutionContext, args: JsonObject) {
  const command = resolveBackgroundCommand(args.task_id);
  if (command.status === "running") {
    command.status = "killed";
    command.child.kill("SIGTERM");
    await waitWithTimeout(command.done, 2000);
  }
  return { task: backgroundPayload(command), killed: command.status === "killed" };
}
