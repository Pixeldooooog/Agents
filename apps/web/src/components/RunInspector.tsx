import { Box, FileText, GitBranch, RefreshCw, ShieldCheck } from "lucide-solid";
import type { Accessor } from "solid-js";
import { createEffect, createSignal, For, Show } from "solid-js";

type TraceData = {
  spans?: Array<Record<string, any>>;
  approvals?: Array<Record<string, any>>;
  artifacts?: Array<Record<string, any>>;
  sandbox_events?: Array<Record<string, any>>;
};

type Props = {
  runId: Accessor<string>;
  baseUrl: Accessor<string>;
  token: Accessor<string>;
  open: Accessor<boolean>;
};

export function RunInspector(props: Props) {
  const [trace, setTrace] = createSignal<TraceData | null>(null);
  const [status, setStatus] = createSignal("idle");

  createEffect(() => {
    if (props.runId()) void loadTrace();
    else setTrace(null);
  });

  const loadTrace = async () => {
    const runId = props.runId();
    if (!runId) return;
    setStatus("loading");
    try {
      const response = await fetch(`${props.baseUrl().replace(/\/$/, "")}/api/v1/agent/runs/${runId}/trace`, {
        headers: props.token().trim() ? { Authorization: `Bearer ${props.token().trim()}` } : {}
      });
      const payload = await response.json();
      if (!response.ok || payload.success === false) throw new Error(payload?.data?.detail || "trace request failed");
      setTrace(payload.data || {});
      setStatus("ready");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error));
    }
  };

  const spans = () => trace()?.spans || [];
  const approvals = () => trace()?.approvals || [];
  const artifacts = () => trace()?.artifacts || [];
  const sandboxEvents = () => trace()?.sandbox_events || [];

  return (
    <aside class="run-inspector" classList={{ "run-inspector-open": props.open() }}>
      <div class="run-inspector-header">
        <div>
          <p class="eyebrow">Trace</p>
          <h2>{props.runId() || "No active run"}</h2>
        </div>
        <button class="icon-button" onClick={loadTrace} disabled={!props.runId()} title="Refresh run trace">
          <RefreshCw size={15} />
        </button>
      </div>

      <div class="trace-counters">
        <Metric icon={<GitBranch size={14} />} label="spans" value={spans().length} />
        <Metric icon={<ShieldCheck size={14} />} label="approvals" value={approvals().length} />
        <Metric icon={<FileText size={14} />} label="artifacts" value={artifacts().length} />
        <Metric icon={<Box size={14} />} label="sandbox" value={sandboxEvents().length} />
      </div>

      <Show when={trace()} fallback={<p class="trace-empty">{status() === "idle" ? "Run details appear after the first request." : status()}</p>}>
        <TraceSection title="Artifacts" items={artifacts()} formatter={(item) => item.workspace_path || item.uri || item.artifact_id} />
        <TraceSection title="Approvals" items={approvals()} formatter={(item) => `${item.decision || "decision"} · ${item.tool_name || item.approval_id || "tool"}`} />
        <TraceSection title="Timeline" items={spans().slice(0, 8)} formatter={(item) => `${item.kind || "span"} · ${item.name || item.span_id}`} />
      </Show>
    </aside>
  );
}

function Metric(props: { icon: any; label: string; value: number }) {
  return (
    <div class="trace-metric">
      {props.icon}
      <strong>{props.value}</strong>
      <span>{props.label}</span>
    </div>
  );
}

function TraceSection(props: { title: string; items: Array<Record<string, any>>; formatter: (item: Record<string, any>) => string }) {
  return (
    <section class="trace-section">
      <h3>{props.title}</h3>
      <Show when={props.items.length > 0} fallback={<p class="trace-empty">No records</p>}>
        <For each={props.items}>{(item) => <p class="trace-row">{props.formatter(item)}</p>}</For>
      </Show>
    </section>
  );
}
