import { Database } from "bun:sqlite";
import { strict as assert } from "node:assert";
import { mkdtemp, rm, copyFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
const root = await mkdtemp(path.join(tmpdir(), "kevin-sqlite-"));
const file = path.join(root, "state.sqlite");
const db = new Database(file);
let peer: Database | undefined;
try {
  db.exec("PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; CREATE TABLE runs(id TEXT PRIMARY KEY); CREATE TABLE actions(id TEXT PRIMARY KEY, run_id TEXT REFERENCES runs(id));");
  assert.equal((db.query("PRAGMA journal_mode").get() as any).journal_mode, "wal");
  assert.throws(() => db.exec("INSERT INTO actions VALUES ('orphan','missing')"));
  assert.throws(() => db.transaction(() => { db.exec("INSERT INTO runs VALUES ('rolled-back')"); throw Error("abort"); })());
  assert.equal((db.query("SELECT count(*) n FROM runs").get() as any).n, 0);
  assert.throws(() => db.transaction(() => { db.exec("CREATE TABLE migration_probe(id); PRAGMA user_version=1"); throw Error("migration abort"); })());
  assert.equal((db.query("PRAGMA user_version").get() as any).user_version, 0);
  assert.equal(db.query("SELECT name FROM sqlite_master WHERE name='migration_probe'").get(), null);
  db.exec("INSERT INTO runs VALUES ('persisted')");
  peer = new Database(file);
  peer.exec("PRAGMA busy_timeout=1");
  db.exec("BEGIN IMMEDIATE");
  assert.throws(() => peer!.exec("INSERT INTO runs VALUES ('concurrent')"));
  db.exec("ROLLBACK");
  peer.exec("INSERT INTO runs VALUES ('after-lock')");
  // Quiescent snapshot: no scheduler or external side effects in this feasibility spike.
  const snapshot = path.join(root, "snapshot.sqlite");
  db.exec(`VACUUM INTO '${snapshot.replaceAll("'", "''")}'`);
  const restored = path.join(root, "restored.sqlite");
  await copyFile(snapshot, restored);
  const child = Bun.spawnSync([process.execPath, "--no-env-file", "-e", 'const {Database}=require("bun:sqlite"); const d=new Database(process.argv[1]); if(d.query("SELECT count(*) n FROM runs").get().n!==2) process.exit(1); d.close();', restored]);
  assert.equal(child.exitCode, 0, child.stderr.toString());
  console.log(JSON.stringify({ sqlite: "pass", checks: ["WAL", "foreign keys", "transaction rollback", "migration rollback", "writer lock", "quiescent snapshot restore", "subprocess reopen"] }));
} finally { peer?.close(); db.close(); await rm(root, { recursive: true, force: true }); }
