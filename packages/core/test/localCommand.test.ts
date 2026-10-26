import { expect, test } from "bun:test";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { startLocalCommand, commandTimeoutMs, COMMAND_STREAM_MAX_BYTES } from "../src/execution/localCommand.js";
import { executeBuiltinTool } from "../src/tools/toolRegistry.js";
import { BoundedOutput } from "../src/execution/boundedOutput.js";

const quote = (s: string) => `'${s.replaceAll("'", "'\\''")}'`;
const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

test("output retention is bounded in bytes without splitting UTF-8", () => {
  const output = new BoundedOutput(5);
  output.append(Buffer.from("你好吗"));
  expect(output.text()).toBe("你");
  expect(output.bytes).toBe(9);
  expect(output.truncated).toBe(true);
  output.append("x".repeat(10000));
  expect(Buffer.byteLength(output.text())).toBeLessThanOrEqual(5);
  const invalid = new BoundedOutput(2);
  invalid.append(Buffer.from([255, 255, 255]));
  expect(Buffer.byteLength(invalid.text())).toBeLessThanOrEqual(2);
  expect(commandTimeoutMs(Infinity)).toBe(30000);
  expect(commandTimeoutMs(0)).toBe(30000);
  expect(commandTimeoutMs(999999999)).toBe(120000);
});

test("foreground and background tools drain large output with explicit truncation", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "kevin-output-"));
  try {
    const command = `${quote(process.execPath)} --no-env-file -e ${quote('process.stdout.write("你".repeat(100000)); process.stderr.write("x".repeat(200000));')}`;
    const raw = startLocalCommand(command, root, 30000);
    await raw.done;
    expect(raw.stdout.bytes).toBe(300000);
    expect(raw.stderr.bytes).toBe(200000);
    expect(Buffer.byteLength(raw.stdout.text())).toBeLessThanOrEqual(COMMAND_STREAM_MAX_BYTES);
    expect(raw.stdout.text()).not.toContain("�");
    const foreground = await executeBuiltinTool(root, "shell.run", { command });
    expect(foreground.result.is_error).toBe(false);
    const result = JSON.parse(foreground.result.content);
    expect(result.original_bytes).toBeGreaterThan(256 * 1024);
    expect(result.truncated).toBe(true);
    expect(Buffer.byteLength(foreground.result.content)).toBeLessThanOrEqual(256 * 1024);
    const background = await executeBuiltinTool(root, "shell.run", { command, run_in_background: true });
    const id = JSON.parse(background.result.content).backgroundTaskId;
    const output = await executeBuiltinTool(root, "shell.output", { task_id: id, max_bytes: 5 });
    const payload = JSON.parse(output.result.content);
    expect(payload.bytes).toBe(500000);
    expect(payload.output).toBe("你");
    expect(payload.truncated).toBe(true);
    expect(payload.task.output_path).toBeUndefined();
  } finally { await rm(root, { recursive: true, force: true }); }
});

async function processRunning(pid: number): Promise<boolean> {
  try {
    process.kill(pid, 0);
    if (process.platform === "linux") {
      const stat = await readFile(`/proc/${pid}/stat`, "utf8");
      if (stat.slice(stat.lastIndexOf(")") + 2).startsWith("Z")) return false;
    }
    return true;
  } catch (error) {
    if (["ESRCH", "ENOENT"].includes((error as NodeJS.ErrnoException).code || "")) return false;
    throw error;
  }
}

for (const mode of ["timeout", "abort", "background-kill"] as const) {
  test(`${mode} reaps a TERM-resistant shell child and grandchild before completion`, async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-process-tree-"));
    const controller = new AbortController();
    let handle: ReturnType<typeof startLocalCommand> | undefined;
    let backgroundId: string | undefined;
    try {
      const script = path.join(root, "fixture.ts");
      await writeFile(script, `import {writeFileSync} from "node:fs"; import {spawn} from "node:child_process";
process.on("SIGTERM", () => {});
const child = process.argv.includes("child");
writeFileSync(${JSON.stringify(root)} + (child ? "/child.pid" : "/parent.pid"), String(process.pid));
if (!child) spawn(process.execPath, ["--no-env-file", import.meta.path, "child"], {stdio: "inherit"});
setInterval(() => {}, 1000);`);
      const command = `${quote(process.execPath)} --no-env-file ${quote(script)}`;
      if (mode === "background-kill") {
        const result = await executeBuiltinTool(root, "shell.run", { command, run_in_background: true });
        backgroundId = JSON.parse(result.result.content).backgroundTaskId;
      } else handle = startLocalCommand(command, root, mode === "timeout" ? 1000 : 30000, controller.signal);
      let pids: number[] = [];
      for (let i = 0; i < 50; i++) {
        try { pids = await Promise.all(["parent", "child"].map(async name => Number(await readFile(path.join(root, `${name}.pid`), "utf8")))); break; }
        catch { await delay(10); }
      }
      expect(pids).toHaveLength(2);
      if (mode === "abort") controller.abort();
      if (mode === "background-kill") {
        const result = await executeBuiltinTool(root, "shell.kill", { task_id: backgroundId });
        expect(JSON.parse(result.result.content).killed).toBe(true);
      } else {
        await handle!.done;
        expect(handle!.status).toBe(mode === "timeout" ? "timed_out" : "killed");
      }
      for (const pid of pids) {
        for (let i = 0; i < 100 && await processRunning(pid); i++) await delay(10);
        expect(await processRunning(pid)).toBe(false);
      }
    } finally {
      handle?.stop();
      await handle?.done;
      if (backgroundId) await executeBuiltinTool(root, "shell.kill", { task_id: backgroundId });
      await rm(root, { recursive: true, force: true });
    }
  });
}

test("pre-aborted execution never spawns a command", async () => {
  const controller = new AbortController(); controller.abort();
  const command = startLocalCommand("exit 99", tmpdir(), 1000, controller.signal);
  await command.done;
  expect(command.status).toBe("killed");
  expect(command.exitCode).toBeNull();
});
