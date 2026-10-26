import { shellRunSchema, shellOutputSchema, shellKillSchema } from "./processSchemas.js";
import { commandTimeoutMs } from "../execution/localCommand.js";
import { localExecutor } from "../execution/localExecutor.js";
import type { JsonObject } from "../types/jsonTypes.js";
import type { ToolDefinition, ToolExecutionContext } from "./toolContracts.js";
import { numberArg, stringArg } from "./toolInputs.js";
import {
  shellBackgrounds,
  shellKill,
  shellOutput,
  startBackgroundCommand
} from "./shellBackgroundTools.js";

export const processToolDefinitions: ToolDefinition[] = [
  {
    name: "shell.run",
    parameters: shellRunSchema,
    description: "Run a shell command in the workspace.",
    risk: "high",
    handler: runShell
  },
  {
    name: "shell.output",
    parameters: shellOutputSchema,
    description: "Read output from a background shell command.",
    risk: "low",
    handler: shellOutput
  },
  {
    name: "shell.backgrounds",
    parameters: { type: "object", properties: {}, additionalProperties: false },
    description: "List background shell commands.",
    risk: "low",
    handler: shellBackgrounds
  },
  {
    name: "shell.kill",
    parameters: shellKillSchema,
    description: "Stop a background shell command.",
    risk: "medium",
    handler: shellKill
  },
  {
    name: "test.discover",
    parameters: { type: "object", properties: {}, additionalProperties: false },
    description: "Suggest likely project test commands.",
    risk: "low",
    handler: discoverTests
  },
  {
    name: "test.run",
    parameters: shellRunSchema,
    description: "Run a test command in the workspace.",
    risk: "high",
    handler: runShell
  },
  {
    name: "sleep.wait",
    description: "Wait for a bounded duration.",
    risk: "low",
    parameters: {
      type: "object",
      properties: {
        duration_seconds: { type: "number", minimum: 0, maximum: 600 },
        seconds: { type: "number", minimum: 0, maximum: 600 },
        reason: { type: "string" }
      }
    },
    handler: sleepWait
  }
];

async function runShell(context: ToolExecutionContext, args: JsonObject) {
  const command = stringArg(args.command);
  if (!command) throw new Error("command is required");
  if (args.dangerouslyDisableSandbox) throw new Error("dangerouslyDisableSandbox is not supported by this runtime");
  const timeoutMs = commandTimeoutMs(args.timeout_ms);
  if (args.run_in_background) {
    return startBackgroundCommand(command, context.repoRoot, timeoutMs, stringArg(args.description, command), context.signal, context.commandExecutor, context.executionPolicy);
  }
  const execution = (context.commandExecutor ?? localExecutor).start({ command, cwd: context.repoRoot, timeoutMs, signal: context.signal, policy: context.executionPolicy ?? { mode: "local" } });
  await execution.done;
  if (["timed_out", "killed", "error"].includes(execution.status)) throw new Error(`command ${execution.status}: ${execution.stderr.text()}`);
  const result = { exit_code: execution.exitCode, stdout: execution.stdout.text(), stderr: execution.stderr.text(),
    stdout_bytes: execution.stdout.bytes, stderr_bytes: execution.stderr.bytes,
    truncated: execution.stdout.truncated || execution.stderr.truncated };
  return { command, timeout_ms: timeoutMs, background: false, ...result };
}

async function discoverTests() {
  return {
    commands: [
      "bun test",
      "bun run typecheck",
      "bun run --cwd apps/terminal app-flow-smoke"
    ]
  };
}

async function sleepWait(context: ToolExecutionContext, args: JsonObject) {
  const requestedSeconds = Math.max(0, Math.min(600, numberArg(args.duration_seconds ?? args.seconds, 1)));
  const startedAt = performance.now();
  const wokeForNotification = requestedSeconds > 0
    ? await waitForSleepOrWake(context, requestedSeconds * 1000)
    : false;
  return {
    requested_seconds: requestedSeconds,
    slept_seconds: Math.max(0, (performance.now() - startedAt) / 1000),
    reason: stringArg(args.reason),
    woke_for_notification: wokeForNotification
  };
}

async function waitForSleepOrWake(context: ToolExecutionContext, milliseconds: number): Promise<boolean> {
  if (context.sleepWake?.isWakeRequested()) return true;
  if (context.sleepWake) return context.sleepWake.wait(milliseconds);
  await new Promise((resolve) => setTimeout(resolve, milliseconds));
  return false;
}
