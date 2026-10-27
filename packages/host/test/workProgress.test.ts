import { expect, test } from "bun:test";
import { collectWorkSteps } from "../../../apps/web/src/runtime/workSteps.js";
import type { OperationEvent } from "../../../apps/web/src/types/operationTypes.js";

const start: OperationEvent = {
  id: "start",
  runId: "run-a",
  toolCallId: "call-1",
  toolName: "filesystem.write",
  scene: "edit",
  phase: "opening",
  title: "Write",
  argsPreview: { path: "note.md" },
  target: "note.md",
};

test("work notebook groups actual calls, preserving their inputs without counting summaries", () => {
  const steps = collectWorkSteps([
    start,
    {
      ...start,
      id: "done",
      phase: "done",
      argsPreview: {},
      target: "filesystem.write",
    },
    {
      ...start,
      id: "summary",
      toolCallId: "",
      scene: "summary",
      phase: "done",
    },
  ]);
  expect(steps).toHaveLength(1);
  expect(steps[0]?.phase).toBe("done");
  expect(steps[0]?.argsPreview).toEqual({ path: "note.md" });
  expect(steps[0]?.target).toBe("note.md");
});

test("same call IDs in distinct runs stay separate and unfinished work stays unfinished", () => {
  const steps = collectWorkSteps([
    start,
    { ...start, runId: "run-b", phase: "error" },
  ]);
  expect(steps.map((step) => step.phase)).toEqual(["opening", "error"]);
});
