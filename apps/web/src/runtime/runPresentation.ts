import type { RuntimeRun } from "../types/agentApiTypes";
import { isRecord } from "./apiValidation";
import { toolDisplayName } from "./workSteps";

export type RunEntry = {
  label: string;
  detail: string;
  time: string;
  payload: Record<string, unknown>;
};

const labels: Record<string, string> = {
  run_created: "开始这次工作",
  tool_start: "开始操作",
  tool_result: "操作返回",
  tool_approval_required: "等待你的确认",
  error: "遇到问题",
  done: "本轮结束",
};

export function presentRun(run: RuntimeRun) {
  let output = "";
  let error = "";
  let durationMs: number | undefined;
  const entries: RunEntry[] = [];
  for (const event of run.events) {
    const type = typeof event.type === "string" ? event.type : "";
    const payload = isRecord(event.payload) ? event.payload : {};
    if (type === "done") {
      if (typeof payload.content === "string") output = payload.content;
      if (typeof payload.error === "string") error = payload.error;
      if (
        typeof payload.duration_ms === "number" &&
        Number.isFinite(payload.duration_ms) &&
        payload.duration_ms >= 0
      )
        durationMs = payload.duration_ms;
    }
    if (type === "error" && typeof payload.message === "string")
      error = payload.message;
    if (!labels[type]) continue;
    const call = isRecord(payload.tool_call) ? payload.tool_call : {};
    const toolName =
      typeof call.name === "string"
        ? call.name
        : typeof event.name === "string"
          ? event.name
          : "";
    entries.push({
      label:
        type === "tool_result" && payload.is_error === true
          ? "操作失败"
          : labels[type]!,
      detail: type.startsWith("tool_")
        ? toolDisplayName(toolName)
        : type === "error"
          ? error
          : "",
      time: typeof event.occurred_at === "string" ? event.occurred_at : "",
      payload,
    });
  }
  const fallback =
    run.status === "waiting_approval"
      ? "这次工作需要你的确认"
      : run.status === "failed"
        ? "这次工作没有完成"
        : run.status === "cancelled"
          ? "已停止的工作"
          : run.status === "completed"
            ? "本轮已结束，没有文字结果"
            : "仍在进行中的工作";
  const summary =
    run.status === "cancelled"
      ? fallback
      : output
          .split("\n")
          .find((line) => line.trim())
          ?.replace(/^\s*#{1,6}\s*/, "")
          .slice(0, 90) || fallback;
  return { output, error, durationMs, entries, summary };
}

export function runDate(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleString("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
