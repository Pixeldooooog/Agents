import { expect, test } from "bun:test";
import { presentRun } from "../../../apps/web/src/runtime/runPresentation.js";
import type { RuntimeRun } from "../../../apps/web/src/types/agentApiTypes.js";

const record = (
  events: RuntimeRun["events"],
  status = "completed",
): RuntimeRun => ({
  run_id: "run-a",
  tenant_id: "",
  user_id: "",
  agent_id: "",
  workspace_id: "",
  created_at: 0,
  updated_at: 0,
  status,
  events,
});

test("run review uses only the selected record and preserves real error/result evidence", () => {
  const first = presentRun(
    record(
      [
        {
          type: "tool_start",
          payload: { tool_call: { name: "filesystem.write" } },
        },
        { type: "tool_result", payload: { is_error: true } },
        {
          type: "done",
          payload: {
            content: "# Partial result",
            error: "disk full",
            duration_ms: 30,
          },
        },
      ],
      "failed",
    ),
  );
  const second = presentRun(
    record([{ type: "done", payload: { content: "Other result" } }]),
  );
  expect(first.summary).toBe("Partial result");
  expect(first.error).toBe("disk full");
  expect(first.durationMs).toBe(30);
  expect(first.entries[1]?.label).toBe("操作失败");
  expect(second.error).toBe("");
  expect(second.entries).toHaveLength(1);
});

test("run review skips text deltas and does not invent completion or timing", () => {
  const result = presentRun(
    record(
      [
        { type: "text_delta", payload: { delta: "unfinished" } },
        { type: "done", payload: { content: "", duration_ms: -1 } },
      ],
      "cancelled",
    ),
  );
  expect(result.output).toBe("");
  expect(result.summary).toBe("已停止的工作");
  expect(result.durationMs).toBeUndefined();
  expect(result.entries).toHaveLength(1);
});
