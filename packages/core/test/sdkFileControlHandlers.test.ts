import { modelStreamResponse } from "./fixtures/modelResponse.js";
import { describe, expect, test } from "bun:test";
import { chmod, mkdir, mkdtemp, readFile, rm, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { AgentSdkClient, rewindEntriesFromToolResult, SdkFileReadStates, type SdkWireMessage } from "@kevin/core/sdk";
import { JsonStateStore, loadSettings, specFromPayload } from "../src/index.js";

describe("SDK file control handlers", () => {
  test("seeds read state for safe writes and rewinds changed files", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-file-controls-"));
    const server = Bun.serve({
      port: 0,
      async fetch(request) {
        const body = await request.json();
        if ((body.messages || []).some((message: any) => message.role === "tool")) {
          return modelStreamResponse({ choices: [{ message: { content: "write complete" } }] });
        }
        return modelStreamResponse({
          choices: [{
            message: {
              content: "",
              tool_calls: [{
                id: "call_sdk_file_write",
                type: "function",
                function: {
                  name: "filesystem__write",
                  arguments: JSON.stringify({ path: "tracked.txt", content: "updated\n" })
                }
              }]
            }
          }]
        });
      }
    });
    try {
      const trackedPath = path.join(root, "tracked.txt");
      await writeFile(trackedPath, "original\n");
      const observedMtime = (await stat(trackedPath)).mtimeMs;
      const client = await sdkClient(root);
      const session = client.createSession({
        sessionId: "file_control_session",
        ...modelOptions(server.port),
        permissionProfile: "auto",
        enabledTools: ["filesystem.write"]
      });

      const seedOutputs = await collectWireMessages(session.runWireMessages([{
        type: "control_request",
        requestId: "seed_1",
        request: { subtype: "seed_read_state", path: "tracked.txt", mtime: observedMtime }
      }]));
      expect(controlPayload(seedOutputs[0])).toMatchObject({
        seeded: true,
        path: "tracked.txt"
      });

      const runOutputs = await collectWireMessages(session.runWireMessages([{
        type: "user_message",
        uuid: "message_file_1",
        sessionId: "file_control_session",
        content: "update tracked file"
      }]));
      expect(runOutputs.at(-1)).toMatchObject({
        type: "result",
        status: "finished",
        isError: false
      });
      expect(await readFile(trackedPath, "utf8")).toBe("updated\n");

      const dryRunOutputs = await collectWireMessages(session.runWireMessages([{
        type: "control_request",
        requestId: "rewind_dry_1",
        request: { subtype: "rewind_files", userMessageId: "message_file_1", dryRun: true }
      }]));
      expect(controlPayload(dryRunOutputs[0])).toMatchObject({
        canRewind: true,
        filesChanged: ["tracked.txt"]
      });

      const rewindOutputs = await collectWireMessages(session.runWireMessages([{
        type: "control_request",
        requestId: "rewind_1",
        request: { subtype: "rewind_files", userMessageId: "message_file_1" }
      }]));
      expect(controlPayload(rewindOutputs[0])).toEqual({ canRewind: true });
      expect(await readFile(trackedPath, "utf8")).toBe("original\n");
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });

  test("seeds only text read state and preserves detected encoding", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-read-state-text-"));
    try {
      const readStates = new SdkFileReadStates();
      const utf16Path = path.join(root, "utf16.txt");
      const binaryPath = path.join(root, "artifact.bin");
      await writeFile(utf16Path, Buffer.concat([Buffer.from([0xff, 0xfe]), Buffer.from("hello\n", "utf16le")]));
      await writeFile(binaryPath, Buffer.from([0, 1, 2, 3, 255]));

      const utf16Seed = await readStates.seedReadState(root, "utf16.txt", (await stat(utf16Path)).mtimeMs, {
        sessionId: "seed_text_session"
      });
      expect(utf16Seed).toMatchObject({ seeded: true, path: "utf16.txt" });
      expect(readStates.forSession("seed_text_session")["utf16.txt"]).toMatchObject({
        content: "hello\n",
        encoding: "utf-16le",
        source: "read",
        fullRead: true
      });

      const binarySeed = await readStates.seedReadState(root, "artifact.bin", (await stat(binaryPath)).mtimeMs, {
        sessionId: "seed_text_session"
      });
      expect(binarySeed).toMatchObject({ seeded: false, path: "artifact.bin" });
      expect(readStates.forSession("seed_text_session")["artifact.bin"]).toBeUndefined();
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("rewinds file-history snapshot backups", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-file-history-"));
    try {
      const store = new JsonStateStore(path.join(root, "state.json"));
      const settings = await loadSettings(root);
      const client = new AgentSdkClient({ settings, store });
      const sessionId = "snapshot_session";
      const messageId = "message_snapshot_1";
      const backupRoot = path.join(root, ".claude", "file-history", sessionId);
      await mkdir(backupRoot, { recursive: true });
      await writeFile(path.join(backupRoot, "tracked@v1"), "original\n");
      await writeFile(path.join(root, "tracked.txt"), "updated\n");

      const run = await store.startRun(specFromPayload({
        message: "snapshot rewind",
        metadata: {
          sdk_session_id: sessionId,
          sdk_user_message_uuid: messageId
        }
      }));
      await store.recordEvent(run.run_id, {
        type: "file-history-snapshot",
        name: "file-history",
        payload: {
          type: "file-history-snapshot",
          messageId,
          sessionId,
          backupRoot,
          snapshot: {
            messageId,
            trackedFileBackups: {
              "tracked.txt": {
                backupFileName: "tracked@v1",
                version: 1,
                backupTime: "2026-06-09T00:00:00.000Z"
              }
            }
          }
        }
      });
      await store.finishRun(run.run_id, "finished");

      const dryRun = await client.rewindFiles(messageId, { sessionId, dryRun: true });
      expect(dryRun).toMatchObject({
        canRewind: true,
        filesChanged: ["tracked.txt"]
      });

      expect(await client.rewindFiles(messageId, { sessionId })).toEqual({ canRewind: true });
      expect(await readFile(path.join(root, "tracked.txt"), "utf8")).toBe("original\n");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("rewinds file-history snapshot bytes and file modes", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-file-history-bytes-"));
    try {
      const store = new JsonStateStore(path.join(root, "state.json"));
      const settings = await loadSettings(root);
      const client = new AgentSdkClient({ settings, store });
      const sessionId = "snapshot_bytes_session";
      const messageId = "message_snapshot_bytes_1";
      const backupRoot = path.join(root, ".claude", "file-history", sessionId);
      const backupPath = path.join(backupRoot, "binary@v1");
      const targetPath = path.join(root, "bin", "tool.bin");
      const originalBytes = Buffer.from([0, 1, 2, 3, 255, 10]);
      const updatedBytes = Buffer.from([9, 8, 7, 6, 0]);
      await mkdir(path.dirname(backupPath), { recursive: true });
      await mkdir(path.dirname(targetPath), { recursive: true });
      await writeFile(backupPath, originalBytes);
      await chmod(backupPath, 0o755);
      await writeFile(targetPath, updatedBytes);
      await chmod(targetPath, 0o644);

      const run = await store.startRun(specFromPayload({
        message: "snapshot bytes rewind",
        metadata: {
          sdk_session_id: sessionId,
          sdk_user_message_uuid: messageId
        }
      }));
      await store.recordEvent(run.run_id, {
        type: "file-history-snapshot",
        name: "file-history",
        payload: {
          type: "file-history-snapshot",
          messageId,
          sessionId,
          backupRoot,
          snapshot: {
            messageId,
            trackedFileBackups: {
              "bin/tool.bin": {
                backupFileName: "binary@v1",
                version: 1,
                backupTime: "2026-06-09T00:00:00.000Z"
              }
            }
          }
        }
      });
      await store.finishRun(run.run_id, "finished");

      expect(await client.rewindFiles(messageId, { sessionId, dryRun: true })).toMatchObject({
        canRewind: true,
        filesChanged: ["bin/tool.bin"]
      });

      expect(await client.rewindFiles(messageId, { sessionId })).toEqual({ canRewind: true });
      expect(Buffer.compare(await readFile(targetPath), originalBytes)).toBe(0);
      expect((await stat(targetPath)).mode & 0o777).toBe(0o755);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("rewinds legacy SDK tool payloads after event message ids", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-legacy-file-rewind-"));
    try {
      const store = new JsonStateStore(path.join(root, "state.json"));
      const settings = await loadSettings(root);
      const client = new AgentSdkClient({ settings, store });
      const sessionId = "legacy_rewind_session";
      const messageId = "legacy_user_message_1";
      await writeFile(path.join(root, "legacy.txt"), "changed\n");

      const run = await store.startRun(specFromPayload({
        message: "legacy rewind",
        metadata: { sdk_session_id: sessionId }
      }));
      await store.recordEvent(run.run_id, {
        type: "user_message",
        payload: { uuid: messageId, message: { content: "edit legacy file" } }
      });
      await store.recordEvent(run.run_id, {
        type: "tool_result",
        name: "Read",
        payload: {
          content: JSON.stringify({
            file: { file_path: "legacy.txt", content: "original\n" },
            content: "original\n"
          })
        }
      });
      await store.recordEvent(run.run_id, {
        type: "tool_result",
        name: "Write",
        payload: {
          content: JSON.stringify({
            file_path: "legacy.txt",
            new_content: "changed\n",
            safety: { required_prior_read: true, encoding: "utf-8" }
          })
        }
      });
      await store.finishRun(run.run_id, "finished");

      const dryRun = await client.rewindFiles(messageId, { sessionId, dryRun: true });
      expect(dryRun).toMatchObject({
        canRewind: true,
        filesChanged: ["legacy.txt"]
      });

      expect(await client.rewindFiles(messageId, { sessionId })).toEqual({ canRewind: true });
      expect(await readFile(path.join(root, "legacy.txt"), "utf8")).toBe("original\n");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("rewinds legacy raw tool result payloads", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-raw-file-rewind-"));
    try {
      const store = new JsonStateStore(path.join(root, "state.json"));
      const settings = await loadSettings(root);
      const client = new AgentSdkClient({ settings, store });
      const sessionId = "raw_rewind_session";
      const messageId = "raw_user_message_1";
      await writeFile(path.join(root, "raw.txt"), "changed\n");

      const run = await store.startRun(specFromPayload({
        message: "raw rewind",
        metadata: { sdk_session_id: sessionId }
      }));
      await store.recordEvent(run.run_id, {
        type: "user_message",
        payload: { uuid: messageId, message: { content: "edit raw file" } }
      });
      await store.recordEvent(run.run_id, {
        type: "tool_result",
        name: "Write",
        payload: {
          raw: {
            result: JSON.stringify({
              file_path: "raw.txt",
              original_file: "original\n",
              new_content: "changed\n"
            })
          }
        }
      });
      await store.finishRun(run.run_id, "finished");

      expect(await client.rewindFiles(messageId, { sessionId, dryRun: true })).toMatchObject({
        canRewind: true,
        filesChanged: ["raw.txt"]
      });

      expect(await client.rewindFiles(messageId, { sessionId })).toEqual({ canRewind: true });
      expect(await readFile(path.join(root, "raw.txt"), "utf8")).toBe("original\n");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("resolves file-history backups from run metadata roots", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-file-history-metadata-root-"));
    try {
      const store = new JsonStateStore(path.join(root, "state.json"));
      const settings = await loadSettings(root);
      const client = new AgentSdkClient({ settings, store });
      const sessionId = "metadata_root_session";
      const messageId = "metadata_root_message_1";
      const backupRoot = path.join(root, "custom-history-root");
      await mkdir(backupRoot, { recursive: true });
      await writeFile(path.join(backupRoot, "tracked@v1"), "original\n");
      await writeFile(path.join(root, "tracked.txt"), "updated\n");

      const run = await store.startRun(specFromPayload({
        message: "metadata root rewind",
        metadata: {
          sdk_session_id: sessionId,
          sdk_user_message_uuid: messageId,
          file_history_root: backupRoot
        }
      }));
      await store.recordEvent(run.run_id, {
        type: "file-history-snapshot",
        name: "file-history",
        payload: {
          type: "file-history-snapshot",
          messageId,
          sessionId,
          snapshot: {
            messageId,
            trackedFileBackups: {
              "tracked.txt": {
                backupFileName: "tracked@v1",
                version: 1,
                backupTime: "2026-06-09T00:00:00.000Z"
              }
            }
          }
        }
      });
      await store.finishRun(run.run_id, "finished");

      expect(await client.rewindFiles(messageId, { sessionId })).toEqual({ canRewind: true });
      expect(await readFile(path.join(root, "tracked.txt"), "utf8")).toBe("original\n");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  test("parses legacy edit payloads with structured multi-file patches", () => {
    const parsed = rewindEntriesFromToolResult({
      type: "tool_result",
      name: "Edit",
      payload: {}
    }, {
      files: [
        { path: "created.txt", action: "create" },
        { path: "edited.txt", action: "edit" }
      ],
      structuredPatches: [{
        path: "created.txt",
        hunks: [{ lines: ["+new line", "+second line"] }]
      }]
    }, new Map());

    expect(parsed.entries).toEqual([{
      path: "created.txt",
      before: "",
      existed: false,
      encoding: "utf-8",
      insertions: 2,
      deletions: 0
    }]);
    expect(parsed.unsupportedPaths).toEqual(["edited.txt"]);
  });

  test("records file-history snapshots during SDK queries", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-file-history-recorder-"));
    const server = Bun.serve({
      port: 0,
      async fetch(request) {
        const body = await request.json();
        if ((body.messages || []).some((message: any) => message.role === "tool")) {
          return modelStreamResponse({ choices: [{ message: { content: "recorded" } }] });
        }
        return modelStreamResponse({
          choices: [{
            message: {
              content: "",
              tool_calls: [{
                id: "call_sdk_history_write",
                type: "function",
                function: {
                  name: "filesystem__write",
                  arguments: JSON.stringify({ path: "history.txt", content: "updated\n" })
                }
              }]
            }
          }]
        });
      }
    });
    try {
      const trackedPath = path.join(root, "history.txt");
      await writeFile(trackedPath, "original\n");
      const store = new JsonStateStore(path.join(root, "state.json"));
      const settings = await loadSettings(root);
      const client = new AgentSdkClient({ settings, store });
      const sessionId = "file_history_recorder_session";
      const session = client.createSession({
        sessionId,
        ...modelOptions(server.port),
        permissionProfile: "auto",
        enabledTools: ["filesystem.write"]
      });
      await client.seedReadState("history.txt", (await stat(trackedPath)).mtimeMs, { sessionId });

      const outputs = await collectWireMessages(session.runWireMessages([{
        type: "user_message",
        uuid: "message_history_1",
        sessionId,
        content: "update history file"
      }]));
      expect(outputs.at(-1)).toMatchObject({ type: "result", status: "finished" });

      const snapshotEvents = (await store.listRuns({ limit: 10 }))
        .flatMap((run) => run.events)
        .filter((event) => event.type === "file-history-snapshot");
      expect(snapshotEvents).toHaveLength(2);
      expect(snapshotEvents[0].payload?.isSnapshotUpdate).toBe(false);
      expect(snapshotEvents[1].payload?.isSnapshotUpdate).toBe(true);
      const snapshot = snapshotEvents[1].payload?.snapshot as Record<string, any>;
      const backup = snapshot.trackedFileBackups["history.txt"];
      const backupRoot = String(snapshotEvents[1].payload?.backupRoot || "");
      expect(backupRoot).toBe(path.join(root, ".kevin", "sdk", "file-history", sessionId));
      expect(backup.backupFileName).toEqual(expect.any(String));
      expect(await readFile(path.join(backupRoot, backup.backupFileName), "utf8")).toBe("original\n");
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });

  test("migrates file-history backups when forking sessions", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-sdk-file-history-fork-"));
    try {
      const store = new JsonStateStore(path.join(root, "state.json"));
      const settings = await loadSettings(root);
      const client = new AgentSdkClient({ settings, store });
      const sourceSessionId = "source_history_session";
      const messageId = "message_fork_1";
      const sourceBackupRoot = path.join(root, ".kevin", "sdk", "file-history", sourceSessionId);
      await mkdir(sourceBackupRoot, { recursive: true });
      await writeFile(path.join(sourceBackupRoot, "history@v1"), "original\n");
      const run = await store.startRun(specFromPayload({
        message: "fork snapshot",
        metadata: {
          sdk_session_id: sourceSessionId,
          sdk_user_message_uuid: messageId
        }
      }));
      await store.recordEvent(run.run_id, {
        type: "file-history-snapshot",
        name: "file-history",
        payload: {
          type: "file-history-snapshot",
          messageId,
          sessionId: sourceSessionId,
          backupRoot: sourceBackupRoot,
          snapshot: {
            messageId,
            trackedFileBackups: {
              "history.txt": {
                backupFileName: "history@v1",
                version: 1,
                backupTime: "2026-06-09T00:00:00.000Z"
              }
            }
          }
        }
      });
      await store.finishRun(run.run_id, "finished");

      const forked = await client.forkSession(sourceSessionId);
      const forkedRun = await store.loadRun(forked.runIds[0]);
      const snapshotEvent = forkedRun?.events.find((event) => event.type === "file-history-snapshot");
      const backupRoot = String(snapshotEvent?.payload?.backupRoot || "");
      expect(snapshotEvent?.payload).toMatchObject({
        sessionId: forked.sessionId,
        backupRoot
      });
      expect(backupRoot).toBe(path.join(root, ".kevin", "sdk", "file-history", forked.sessionId));
      expect(await readFile(path.join(backupRoot, "history@v1"), "utf8")).toBe("original\n");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });
});

async function sdkClient(root: string): Promise<AgentSdkClient> {
  const settings = await loadSettings(root);
  return new AgentSdkClient({ settings, store: new JsonStateStore(path.join(root, "state.json")) });
}

function modelOptions(port: number) {
  return {
    protocol: "openai-chat",
    model: "mock",
    baseUrl: `http://127.0.0.1:${port}/v1`,
    apiKey: "test"
  };
}

async function collectWireMessages(messages: AsyncIterable<SdkWireMessage>): Promise<SdkWireMessage[]> {
  const collected: SdkWireMessage[] = [];
  for await (const message of messages) collected.push(message);
  return collected;
}

function controlPayload(message: SdkWireMessage): Record<string, any> {
  if (message.type !== "control_response" || message.response.subtype !== "success") {
    throw new Error("expected control success response");
  }
  return message.response.response as Record<string, any>;
}
