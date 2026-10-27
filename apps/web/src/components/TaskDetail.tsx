import { For, Show } from "solid-js";
import type { TaskRecord, TaskStepRecord } from "../types/runtimeTypes";
import { statusLabel } from "../copy";
import { MessageContent } from "./MessageContent";

export function TaskDetail(props: {
  task?: TaskRecord;
  steps: TaskStepRecord[];
  loading: boolean;
  canReviewApproval: boolean;
  openChat: () => void;
}) {
  return (
    <aside class="task-notebook" aria-label="任务详情">
      <Show
        when={props.task}
        fallback={
          <div class="task-detail-empty">
            <span aria-hidden="true">↖</span>
            <h2>每一件事，都有下文。</h2>
            <p>选中一项任务，在这里查看目标、执行记录与结果。</p>
          </div>
        }
      >
        <div class="task-detail-heading">
          <p class="eyebrow">这件事的来龙去脉</p>
          <h2>{props.task!.title}</h2>
          <span class={`task-status status-${props.task!.status}`}>
            {statusLabel(props.task!.status)}
          </span>
        </div>
        <Show when={props.task!.input !== props.task!.title}>
          <section class="task-objective">
            <h3>交给 Kevin 的事</h3>
            <p>{props.task!.input}</p>
          </section>
        </Show>
        <Show when={props.task!.status === "waiting_approval"}>
          <div class="task-approval-note">
            <p>这件事需要你的确认。</p>
            <Show
              when={props.canReviewApproval}
              fallback={
                <p>当前页面未加载这次运行的审批内容，暂时无法在这里确认。</p>
              }
            >
              <button class="plain-button" onClick={props.openChat}>
                去对话查看待确认操作
              </button>
            </Show>
          </div>
        </Show>
        <section class="task-results">
          <h3>
            执行记录 <span>{props.steps.length}</span>
          </h3>
          <Show
            when={!props.loading}
            fallback={<p role="status">正在翻开这份记录…</p>}
          >
            <Show
              when={props.steps.length}
              fallback={
                <p class="task-detail-hint">
                  还没有执行记录。准备好后，点击「开始」。
                </p>
              }
            >
              <For each={props.steps}>
                {(step, index) => (
                  <article class="task-result">
                    <header>
                      <span>第 {index() + 1} 次执行</span>
                      <span class={`status-${step.status}`}>
                        {statusLabel(step.status)}
                      </span>
                    </header>
                    <Show when={step.output}>
                      <MessageContent content={step.output} />
                    </Show>
                    <Show when={step.error}>
                      <details open>
                        <summary>查看失败原因</summary>
                        <pre>{step.error}</pre>
                      </details>
                    </Show>
                    <Show when={!step.output && !step.error}>
                      <p class="task-detail-hint">暂时没有返回内容。</p>
                    </Show>
                  </article>
                )}
              </For>
            </Show>
          </Show>
        </section>
      </Show>
    </aside>
  );
}
