import { expect, test } from "bun:test";

import { createAgentConversationActions } from "../../../apps/web/src/runtime/agentConversationActions.js";
import { createApiClient } from "../../../apps/web/src/runtime/apiClient.js";
import type {
  ChatMessage,
  ToolApprovalRequest,
} from "../../../apps/web/src/types/runtimeTypes.js";

test("pending approval blocks new turns and duplicate decisions without losing the draft", async () => {
  const request: ToolApprovalRequest = {
    approvalId: "approval-1",
    runId: "run-1",
    toolName: "filesystem.write",
    arguments: {},
    reason: "",
    impact: {},
  };
  let draft = "next question";
  let running = false;
  let approvals = [request];
  let currentRun = "run-1";
  type Options = Parameters<typeof createAgentConversationActions>[0];
  const input = () => draft;
  const setInput: Options["setInput"] = (value) =>
    (draft = typeof value === "function" ? value(draft) : value);
  const busy = () => running;
  const setBusy: Options["setBusy"] = (value) =>
    (running = typeof value === "function" ? value(running) : value);
  const pendingApprovals = () => approvals;
  const setPendingApprovals: Options["setPendingApprovals"] = (value) =>
    (approvals = typeof value === "function" ? value(approvals) : value);
  const runId = () => currentRun;
  const setRunId: Options["setRunId"] = (value) =>
    (currentRun = typeof value === "function" ? value(currentRun) : value);
  const setLatency: Options["setLatency"] = (value) =>
    typeof value === "function" ? value(null) : value;
  const setActivity: Options["setActivity"] = (value) =>
    typeof value === "function" ? value([]) : value;
  const setOperations: Options["setOperations"] = (value) =>
    typeof value === "function" ? value([]) : value;
  const messages: ChatMessage["role"][] = [];
  let calls = 0;
  let failNext = false;
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const server = Bun.serve({
    port: 0,
    hostname: "127.0.0.1",
    async fetch() {
      calls++;
      await gate;
      return Response.json({
        success: true,
        code: "200",
        message: "success",
        data: {
          run_id: "run-1",
          status: failNext ? "failed" : "completed",
          content: failNext ? "" : "done",
          events: failNext
            ? [
                {
                  type: "error",
                  payload: { message: "provider rejected request" },
                },
              ]
            : [],
        },
      });
    },
  });
  const record = () => 1;
  const deps = { setRunId, runId, setPendingApprovals, record };
  const actions = createAgentConversationActions({
    api: () =>
      createApiClient({
        baseUrl: () => server.url.toString(),
        token: () => "",
      }),
    input,
    setInput,
    busy,
    setBusy,
    pendingApprovals,
    streaming: () => false,
    payload: (message) => ({ message }),
    setRunId,
    setLatency,
    setActivity,
    setOperations,
    setPendingApprovals,
    push: (role) => {
      messages.push(role);
      return messages.length;
    },
    removeMessage: () => {},
    record,
    updateActivity: () => {},
    refreshRuns: async () => {},
    syncOperationTrace: async () => {},
    eventDeps: () => deps,
    streamDeps: () => ({
      ...deps,
      updateMessage: () => {},
      updateActivity: () => {},
      removeMessage: () => {},
      push: () => 1,
    }),
  });
  try {
    await actions.send();
    expect(input()).toBe("next question");
    expect(pendingApprovals()).toEqual([request]);
    expect(messages).toEqual([]);
    const first = actions.decideApproval(request, "allow_once");
    await actions.decideApproval(request, "allow_once");
    expect(busy()).toBe(true);
    release();
    await first;
    expect(calls).toBe(1);
    expect(pendingApprovals()).toEqual([]);
    expect(messages).toEqual(["assistant"]);
    await actions.decideApproval(request, "allow_once");
    expect(calls).toBe(1);
    failNext = true;
    await actions.send();
    expect(messages).toEqual(["assistant", "user", "error"]);
  } finally {
    release();
    await server.stop(true);
  }
});
