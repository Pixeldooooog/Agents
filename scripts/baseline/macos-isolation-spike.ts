import { strict as assert } from "node:assert";
import { mkdtemp, mkdir, writeFile, readFile, rm, realpath } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
if (process.platform !== "darwin") throw Error("macOS-only spike; other platforms remain unverified");
const root = await realpath(await mkdtemp(path.join(tmpdir(), "kevin-isolation-")));
const workspace = path.join(root, "workspace");
const outside = path.join(root, "outside");
try {
  await mkdir(workspace); await writeFile(outside, "sentinel");
  const profile = path.join(root, "profile.sb");
  await writeFile(profile, `(version 1)(allow default)(deny network*)(deny file-read* (literal "${outside}"))(deny file-write*)(allow file-write* (subpath "${workspace}") (literal "/dev/null"))`);
  const run = (args: string[], isolated = true) => Bun.spawnSync(isolated ? ["/usr/bin/sandbox-exec", "-f", profile, ...args] : args, { env: { PATH: "/usr/bin:/bin" }, cwd: workspace });
  assert.equal(run(["/bin/cat", outside], false).exitCode, 0);
  assert.notEqual(run(["/bin/cat", outside]).exitCode, 0);
  assert.equal(run(["/bin/sh", "-c", 'echo allowed > allowed.txt']).exitCode, 0);
  assert.equal((await readFile(path.join(workspace, "allowed.txt"), "utf8")).trim(), "allowed");
  assert.notEqual(run(["/bin/sh", "-c", 'echo changed > "$1"', "sh", outside]).exitCode, 0);
  assert.equal(await readFile(outside, "utf8"), "sentinel");
  const listener = Bun.listen({ hostname: "127.0.0.1", port: 0, socket: { data() {}, open(socket) { socket.end(); } } });
  try {
    assert.equal(run(["/usr/bin/nc", "-z", "-w", "1", "127.0.0.1", String(listener.port)], false).exitCode, 0);
    assert.notEqual(run(["/usr/bin/nc", "-z", "-w", "1", "127.0.0.1", String(listener.port)]).exitCode, 0);
  } finally { listener.stop(true); }
  assert.equal(run(["/usr/bin/env"]).stdout.toString().includes("API_KEY"), false);
  console.log(JSON.stringify({ macos: "pass", checks: ["outside sentinel read/write denied", "workspace write allowed", "network denied with positive control", "explicit environment"] , limitation: "feasibility profile only; not production filesystem allowlist or runtime integration" }));
} finally { await rm(root, { recursive: true, force: true }); }
