import { For, Show, createMemo } from "solid-js";
import type { RuntimeRun } from "../types/runtimeTypes";
import { presentRun, runDate } from "../runtime/runPresentation";
import { statusLabel } from "../copy";
import { MessageContent } from "./MessageContent";
import { FailureNotice } from "./FailureNotice";

export function RunInspector(props: {
  run?: RuntimeRun;
  ref?: (element: HTMLElement) => void;
}) {
  const presentation = createMemo(() =>
    props.run ? presentRun(props.run) : undefined,
  );
  return (
    <aside
      class="run-journal"
      aria-label="运行回顾"
      ref={props.ref}
      tabindex="-1"
    >
      <Show
        when={props.run}
        fallback={
          <div class="journal-empty">
            <span aria-hidden="true">↖</span>
            <h2>做过的事，值得留下。</h2>
            <p>选一条记录，看看当时的结果和过程。</p>
          </div>
        }
      >
        <header class="journal-heading">
          <p class="eyebrow">这一次，我们做了什么</p>
          <h2>运行回顾</h2>
          <div>
            <time>{runDate(props.run!.created_at)}</time>
            <span class={`task-status status-${props.run!.status}`}>
              {statusLabel(props.run!.status)}
            </span>
          </div>
        </header>
        <Show when={props.run!.status !== "cancelled" && presentation()?.error}>
          <FailureNotice detail={presentation()!.error} />
        </Show>
        <section class="journal-result">
          <h3>留下的结果</h3>
          <Show
            when={
              presentation()?.output &&
              !(
                props.run!.status === "cancelled" &&
                presentation()?.output === "run canceled"
              )
            }
            fallback={
              <p class="journal-muted">
                {props.run!.status === "waiting_approval"
                  ? "本轮暂停在确认环节。"
                  : props.run!.status === "cancelled"
                    ? "本轮已停止，没有完整结果。"
                    : "这条记录没有文字结果。"}
              </p>
            }
          >
            <MessageContent content={presentation()!.output} />
          </Show>
        </section>
        <section class="journal-events">
          <h3>
            过程回看 <span>{presentation()?.entries.length}</span>
          </h3>
          <Show
            when={presentation()?.entries.length}
            fallback={<p class="journal-muted">没有可展示的过程事件。</p>}
          >
            <ol>
              <For each={presentation()?.entries}>
                {(entry) => (
                  <li>
                    <span class="journal-event-dot" aria-hidden="true" />
                    <div>
                      <div class="journal-event-heading">
                        <strong>{entry.label}</strong>
                        <Show when={entry.time}>
                          <time>
                            {new Date(entry.time).toLocaleTimeString("zh-CN", {
                              hour12: false,
                            })}
                          </time>
                        </Show>
                      </div>
                      <Show when={entry.detail}>
                        <p>{entry.detail}</p>
                      </Show>
                      <details>
                        <summary>事件详情</summary>
                        <pre>{JSON.stringify(entry.payload, null, 2)}</pre>
                      </details>
                    </div>
                  </li>
                )}
              </For>
            </ol>
          </Show>
        </section>
        <footer class="journal-metadata">
          <span>运行编号</span>
          <code>{props.run!.run_id}</code>
          <Show when={presentation()?.durationMs !== undefined}>
            <span>服务记录用时</span>
            <code>{(presentation()!.durationMs! / 1000).toFixed(2)} 秒</code>
          </Show>
          <p>这是历史记录。查看它不会改变当前对话。</p>
        </footer>
      </Show>
    </aside>
  );
}
