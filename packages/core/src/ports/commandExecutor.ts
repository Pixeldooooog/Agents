/** Trusted service policy; never constructed from model tool arguments. */
export type ExecutionPolicy = { mode: "local" } | {
  mode: "isolated";
  filesystem: { readPaths: string[]; writePaths: string[] };
  network: { mode: "deny" | "allowlist"; hosts: string[] };
  environment: { allowedNames: string[] };
};
export type CommandStatus = "running" | "completed" | "failed" | "killed" | "timed_out" | "error";
export interface CommandOutput {
  readonly bytes: number;
  readonly truncated: boolean;
  text(): string;
}
export interface CommandExecution {
  readonly status: CommandStatus;
  readonly exitCode: number | null;
  readonly stdout: CommandOutput;
  readonly stderr: CommandOutput;
  readonly done: Promise<void>;
  stop(): void;
}
export interface CommandExecutor {
  readonly capabilities: {
    backend: "local" | "windows-mxc" | "macos-native" | "linux-native" | "container";
    isolation: "none" | "os";
    cancellation: "process-group" | "os-tree" | "none";
  };
  start(request: {
    command: string;
    cwd: string;
    timeoutMs: number;
    policy: ExecutionPolicy;
    signal?: AbortSignal;
  }): CommandExecution;
}
