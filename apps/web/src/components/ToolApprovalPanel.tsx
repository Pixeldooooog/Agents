import { Check, ShieldX, Wrench } from "lucide-solid";
import type { Accessor } from "solid-js";
import { For, Show } from "solid-js";
import type {
  ApprovalDecision,
  ToolApprovalRequest,
} from "../types/runtimeTypes";
import { toolDisplayName } from "../runtime/workSteps";
import { copy } from "../copy";

type Props = {
  requests: Accessor<ToolApprovalRequest[]>;
  busy: Accessor<boolean>;
  decide: (request: ToolApprovalRequest, decision: ApprovalDecision) => void;
};

export function ToolApprovalPanel(props: Props) {
  return (
    <Show when={props.requests().length > 0}>
      <div class="approval-panel" aria-label="待确认操作">
        <div class="approval-intro">
          <span>需要你点个头</span>
          <h3>这一步，你来决定。</h3>
          <p>确认下面的操作后，我再继续。</p>
        </div>
        <For each={props.requests()}>
          {(request) => (
            <article class="approval-row">
              <div class="approval-icon">
                <Wrench size={15} />
              </div>
              <div class="approval-copy">
                <div class="approval-title">
                  <strong>{toolDisplayName(request.toolName)}</strong>
                  <Show when={request.impact?.risk}>
                    <span class={`risk-pill risk-${request.impact.risk}`}>
                      {copy.approval.risk[request.impact.risk!] ||
                        request.impact.risk}
                    </span>
                  </Show>
                </div>
                <span>
                  {request.reason === "tool requires approval"
                    ? "此操作需要你的确认"
                    : request.reason || copy.approval.reasonFallback}
                </span>
                <Show when={approvalTarget(request)}>
                  <p class="approval-target">{approvalTarget(request)}</p>
                </Show>
                <details class="approval-arguments">
                  <summary>查看完整参数</summary>
                  <p>{request.toolName}</p>
                  <pre>{JSON.stringify(request.arguments, null, 2)}</pre>
                </details>
                <Show when={impactItems(request).length > 0}>
                  <div class="approval-meta">
                    <For each={impactItems(request)}>
                      {(item) => <span>{item}</span>}
                    </For>
                  </div>
                </Show>
                <Show when={request.impact?.diff_preview}>
                  <pre class="approval-diff">{request.impact.diff_preview}</pre>
                </Show>
              </div>
              <div class="approval-actions">
                <button
                  class="approval-choice deny-button"
                  disabled={props.busy()}
                  onClick={() => props.decide(request, "deny")}
                  title={copy.approval.deny}
                >
                  <ShieldX size={15} />
                  <span>{copy.approval.deny}</span>
                </button>
                <button
                  class="approval-choice approve-once-button"
                  disabled={props.busy()}
                  onClick={() => props.decide(request, "allow_once")}
                  title={copy.approval.allowOnce}
                >
                  <Check size={15} />
                  <span>{copy.approval.allowOnce}</span>
                </button>
              </div>
            </article>
          )}
        </For>
      </div>
    </Show>
  );
}

function impactItems(request: ToolApprovalRequest) {
  const impact = request.impact || {};
  const items: string[] = [];
  for (const [label, value] of [
    [copy.approval.impactPath, impact.paths],
    [copy.approval.impactCommand, impact.commands],
    [copy.approval.impactDomain, impact.domains],
  ] as const) {
    if (Array.isArray(value))
      items.push(...value.map((item) => `${label}：${item}`));
  }
  if (impact.cost_estimate)
    items.push(
      `${copy.approval.impactCost}：${JSON.stringify(impact.cost_estimate)}`,
    );
  return items;
}

function approvalTarget(request: ToolApprovalRequest): string {
  for (const field of ["path", "command", "url"]) {
    const value = request.arguments[field];
    if (typeof value === "string") return value;
  }
  return "";
}
