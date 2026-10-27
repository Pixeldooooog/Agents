import { Check, Circle, LoaderCircle, X, AlertCircle } from "lucide-solid";
import { For, Show, createMemo } from "solid-js";
import type { Accessor } from "solid-js";
import { collectWorkSteps, workStepTitle } from "../runtime/workSteps";
import type { OperationEvent, OperationPhase } from "../types/runtimeTypes";

const phaseLabels: Record<OperationPhase, string> = {
  opening: "准备",
  running: "执行中",
  closing: "收尾",
  done: "已完成",
  error: "出错了",
};

export function WorkProgress(props: {
  operations: Accessor<OperationEvent[]>;
  busy: Accessor<boolean>;
  close: () => void;
}) {
  const steps = createMemo(() => collectWorkSteps(props.operations()));
  const completed = () =>
    steps().filter((event) => event.phase === "done").length;
  const label = (event: OperationEvent) =>
    !props.busy() && ["opening", "running", "closing"].includes(event.phase)
      ? "未收到完成结果"
      : phaseLabels[event.phase];
  return (
    <aside class="work-notebook" aria-label="工作过程">
      <header>
        <div>
          <p class="eyebrow">边做，边记</p>
          <h2>
            工作手记<span> / {String(steps().length).padStart(2, "0")}</span>
          </h2>
        </div>
        <button
          class="icon-button"
          aria-label="收起工作过程"
          onClick={props.close}
        >
          <X size={16} />
        </button>
      </header>
      <p class="work-summary">
        {steps().length
          ? `${completed()} 个步骤已完成 · ${props.busy() ? "仍在继续" : "本轮记录"}`
          : "每一步，都有迹可循。"}
      </p>
      <Show
        when={steps().length}
        fallback={
          <div class="work-empty">
            <span aria-hidden="true">···</span>
            <h3>还没有工具步骤</h3>
            <p>Kevin 开始查资料、读文件或执行操作时，记录会出现在这里。</p>
            <small>只展示实际发生的操作。</small>
          </div>
        }
      >
        <ol class="work-steps">
          <For each={steps()}>
            {(event, index) => (
              <li class={`work-step phase-${event.phase}`}>
                <div class="work-step-mark">
                  <Show
                    when={event.phase === "done"}
                    fallback={
                      <Show
                        when={event.phase === "error"}
                        fallback={
                          <Show
                            when={props.busy()}
                            fallback={<Circle size={14} />}
                          >
                            <LoaderCircle size={14} />
                          </Show>
                        }
                      >
                        <AlertCircle size={14} />
                      </Show>
                    }
                  >
                    <Check size={14} />
                  </Show>
                </div>
                <div class="work-step-content">
                  <div class="work-step-label">
                    <span>步骤 {String(index() + 1).padStart(2, "0")}</span>
                    <span>{label(event)}</span>
                  </div>
                  <h3>{workStepTitle(event)}</h3>
                  <Show when={event.target}>
                    <p class="work-target">{event.target}</p>
                  </Show>
                  <details>
                    <summary>查看操作详情</summary>
                    <dl>
                      <dt>工具</dt>
                      <dd>{event.toolName}</dd>
                      <Show when={event.argsPreview}>
                        <dt>输入</dt>
                        <dd>
                          <pre>
                            {JSON.stringify(event.argsPreview, null, 2)}
                          </pre>
                        </dd>
                      </Show>
                      <Show when={event.resultPreview !== undefined}>
                        <dt>结果</dt>
                        <dd>
                          <pre>
                            {typeof event.resultPreview === "string"
                              ? event.resultPreview
                              : JSON.stringify(event.resultPreview, null, 2)}
                          </pre>
                        </dd>
                      </Show>
                    </dl>
                  </details>
                </div>
              </li>
            )}
          </For>
        </ol>
      </Show>
      <footer>看得见过程，才放心交给我。</footer>
    </aside>
  );
}
