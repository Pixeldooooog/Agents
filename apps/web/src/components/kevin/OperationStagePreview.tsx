import { OperationStage } from "../OperationStage";

/** Retained design reference, deliberately separate from live product progress. */
export function OperationStagePreview() {
  return (
    <main class="design-content">
      <h1>操作舞台 · 旧版设计存档</h1>
      <p>此页面只保留旧版视觉方案，不连接当前会话或执行工具。</p>
      <OperationStage operations={() => []} busy={() => false} runId={() => ""} />
    </main>
  );
}
