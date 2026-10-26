import type { CommandExecutor } from "../ports/commandExecutor.js";
import { startLocalCommand } from "./localCommand.js";

/** Explicit host execution. Native sandbox backends are deferred, not silently emulated. */
export const localExecutor: CommandExecutor = {
  capabilities: { backend: "local", isolation: "none", cancellation: process.platform === "win32" ? "none" : "process-group" },
  start(request) {
    if (request.policy.mode !== "local") throw new Error("isolation_unavailable: local executor cannot enforce isolated policy");
    return startLocalCommand(request.command, request.cwd, request.timeoutMs, request.signal);
  }
};
