import { CheckCircle2, Monitor } from "lucide-solid";
import type { Accessor } from "solid-js";
import { For, Show, createEffect, createMemo, createSignal, onCleanup } from "solid-js";
import { playbackDelay, playbackFrames } from "../runtime/operationPlayback";
import type { OperationEvent } from "../types";
import { OperationScene, SceneIcon, StatusMark, sceneLabel } from "./OperationStageScenes";

type Props = {
  operations: Accessor<OperationEvent[]>;
  busy: Accessor<boolean>;
  runId: Accessor<string>;
};

export function OperationStage(props: Props) {
  const latest = createMemo(() => {
    const items = props.operations();
    return items.length ? items[items.length - 1] : undefined;
  });
  const [visible, setVisible] = createSignal<OperationEvent | undefined>();
  const history = createMemo(() => props.operations().slice(-6).reverse());
  const completed = createMemo(() => props.operations().filter((event) => event.phase === "done").length);
  let timers: number[] = [];
  let consumed = 0;

  createEffect(() => {
    const items = props.operations();
    if (!items.length) {
      timers.forEach((timer) => window.clearTimeout(timer));
      timers = [];
      consumed = 0;
      setVisible(undefined);
      return;
    }
    if (items.length < consumed) consumed = 0;
    const pending = items.slice(consumed);
    consumed = items.length;
    if (!pending.length) return;
    timers.forEach((timer) => window.clearTimeout(timer));
    timers = [];
    let offset = 0;
    pending.slice(-14).forEach((event) => {
      playbackFrames(event).forEach((frame, index) => {
        timers.push(window.setTimeout(() => setVisible(frame), offset + playbackDelay(index)));
      });
      offset += event.source === "sandbox_trace" ? 380 : 980;
    });
  });
  onCleanup(() => timers.forEach((timer) => window.clearTimeout(timer)));

  return (
    <aside class="operation-stage-shell">
      <header class="operation-stage-head">
        <div>
          <p class="eyebrow">Workspace computer</p>
          <h2>{visible()?.title || "Agent desktop is idle"}</h2>
        </div>
        <div class="stage-head-meta">
          <span class="stage-run-pill" classList={{ live: props.busy() }}>
            <Monitor size={14} />
            {props.runId() || "no run"}
          </span>
          <span class="stage-count-pill">
            <CheckCircle2 size={14} />
            {completed()} done
          </span>
        </div>
      </header>

      <section class="operation-stage-screen" classList={{ idle: !latest() }}>
        <div class="stage-os-bar">
          <div class="stage-current">
            <StatusMark status={visible()?.phase || "done"} />
            <span>{visible() ? sceneLabel(visible()!.scene) : "Ready"}</span>
          </div>
          <span>{visible()?.target || "Waiting for the next workspace action"}</span>
        </div>
        <Show when={visible()} fallback={<EmptyStage />}>
          <OperationScene event={visible()!} />
        </Show>
      </section>

      <footer class="operation-history" aria-label="Recent operations">
        <For each={history()}>
          {(event) => (
            <article class="operation-history-row" classList={{ active: event.id === latest()?.id }}>
              <span class="history-icon"><SceneIcon scene={event.scene} /></span>
              <div>
                <strong>{sceneLabel(event.scene)}</strong>
                <p>{event.target || event.toolName}</p>
              </div>
              <StatusMark status={event.phase} />
            </article>
          )}
        </For>
      </footer>
    </aside>
  );
}

function EmptyStage() {
  return (
    <div class="empty-stage">
      <Monitor size={38} />
      <h3>Ready to operate</h3>
      <p>Tool calls replay here as file windows, browser searches, documents, terminals, and run summaries.</p>
    </div>
  );
}
