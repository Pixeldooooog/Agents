import { Check, ShieldCheck, ShieldX, Wrench } from "lucide-solid";
import type { Accessor } from "solid-js";
import { For, Show } from "solid-js";
import type { ApprovalDecision, ToolApprovalRequest } from "../types/runtimeTypes";
import { copy } from "../copy";

type Props = {
  requests: Accessor<ToolApprovalRequest[]>;
  busy: Accessor<boolean>;
  decide: (request: ToolApprovalRequest, decision: ApprovalDecision) => void;
};

export function ToolApprovalPanel(props: Props) {
  return (
    <Show when={props.requests().length > 0}>
      <div class="approval-panel">
        <For each={props.requests()}>{(request) => (
          <article class="approval-row">
            <div class="approval-icon"><Wrench size={15} /></div>
            <div class="approval-copy">
              <div class="approval-title">
                <strong>{request.toolName}</strong>
                <Show when={request.impact?.risk}>
                  <span class={`risk-pill risk-${request.impact.risk}`}>{copy.approval.risk[request.impact.risk!] || request.impact.risk}</span>
                </Show>
              </div>
              <span>{request.reason || copy.approval.reasonFallback}</span>
              <code>{compactArgs(request.arguments)}</code>
              <Show when={impactItems(request).length > 0}>
                <div class="approval-meta">
                  <For each={impactItems(request)}>{(item) => <span>{item}</span>}</For>
                </div>
              </Show>
              <Show when={request.impact?.diff_preview}>
                <pre class="approval-diff">{request.impact.diff_preview}</pre>
              </Show>
            </div>
            <div class="approval-actions">
              <button class="approval-choice deny-button" disabled={props.busy()} onClick={() => props.decide(request, "deny")} title={copy.approval.deny}>
                <ShieldX size={15} />
                <span>{copy.approval.deny}</span>
              </button>
              <button class="approval-choice approve-once-button" disabled={props.busy()} onClick={() => props.decide(request, "allow_once")} title={copy.approval.allowOnce}>
                <Check size={15} />
                <span>{copy.approval.allowOnce}</span>
              </button>
              <button class="approval-choice approve-run-button" disabled={props.busy()} onClick={() => props.decide(request, "allow_for_run")} title={copy.approval.allowForRun}>
                <ShieldCheck size={15} />
                <span>{copy.approval.allowForRun}</span>
              </button>
            </div>
          </article>
        )}</For>
      </div>
    </Show>
  );
}

function compactArgs(args: Record<string, unknown>) {
  const text = JSON.stringify(args || {});
  return text.length > 140 ? `${text.slice(0, 137)}...` : text;
}

function impactItems(request: ToolApprovalRequest) {
  const impact = request.impact || {};
  const items: string[] = [];
  for (const [label, value] of [
    [copy.approval.impactPath, impact.paths],
    [copy.approval.impactCommand, impact.commands],
    [copy.approval.impactDomain, impact.domains]
  ] as const) {
    if (Array.isArray(value)) items.push(...value.slice(0, 2).map((item) => `${label}：${item}`));
  }
  if (impact.cost_estimate) items.push(`${copy.approval.impactCost}：${JSON.stringify(impact.cost_estimate)}`);
  return items;
}
