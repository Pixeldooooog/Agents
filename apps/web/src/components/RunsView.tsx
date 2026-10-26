import { RefreshCw } from "lucide-solid";
import type { Accessor, Setter } from "solid-js";
import { For, Show } from "solid-js";
import type { ActivityEvent, RuntimeRun } from "../types/runtimeTypes";
import { ActionTimeline } from "./ActionTimeline";
import { RunInspector } from "./RunInspector";
import { copy, statusLabel } from "../copy";

type Props = {
  runs: Accessor<RuntimeRun[]>;
  runId: Accessor<string>;
  setRunId: Setter<string>;
  activity: Accessor<ActivityEvent[]>;
  baseUrl: Accessor<string>;
  token: Accessor<string>;
  refreshRuns: () => Promise<void>;
};

export function RunsView(props: Props) {
  return (
    <section class="split-view">
      <article class="panel-card">
        <div class="panel-header">
          <div><p class="eyebrow">{copy.runs.eyebrow}</p><h2>{copy.runs.title}</h2></div>
          <button class="icon-button" title={copy.runs.refresh} aria-label={copy.runs.refresh} onClick={() => void props.refreshRuns()}><RefreshCw size={15} /></button>
        </div>
        <div class="table-head">
          <span>{copy.runs.columnId}</span><span>{copy.runs.columnStatus}</span><span>{copy.runs.columnUpdated}</span>
        </div>
        <div class="table-body">
          <Show when={props.runs().length > 0} fallback={<p class="trace-empty">{copy.runs.empty}</p>}>
            <For each={props.runs()}>{(run) => (
              <button class="table-row" classList={{ active: props.runId() === run.run_id }} onClick={() => props.setRunId(run.run_id)}>
                <span>{run.run_id}</span>
                <span class={`status-${run.status}`}>{statusLabel(run.status)}</span>
                <span>{timeText(run.updated_at)}</span>
              </button>
            )}</For>
          </Show>
        </div>
      </article>

      <div class="side-stack side-stack-open">
        <ActionTimeline events={props.activity} open={() => true} />
        <RunInspector runId={props.runId} baseUrl={props.baseUrl} token={props.token} open={() => true} />
      </div>
    </section>
  );
}

function timeText(value: number) {
  if (!value) return "-";
  return new Date(value * 1000).toLocaleString();
}
