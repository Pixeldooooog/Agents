import { Eraser, MessageSquareText, Send, Square } from "lucide-solid";
import type { Accessor, Setter } from "solid-js";
import { For, Show } from "solid-js";
import type { ApprovalDecision, ChatMessage, PermissionMode, ToolApprovalRequest } from "../types/runtimeTypes";
import { ToolApprovalPanel } from "./ToolApprovalPanel";
import { copy } from "../copy";

import { KevinAvatar, type KevinState } from "./kevin/KevinAvatar";
import { AgentPresence } from "./kevin/Primitives";

type Props = {
  agentState: Accessor<KevinState>;
  messages: Accessor<ChatMessage[]>;
  busy: Accessor<boolean>;
  protocol: Accessor<string>;
  model: Accessor<string>;
  permissionMode: Accessor<PermissionMode>;
  latency: Accessor<number | null>;
  toolCount: Accessor<number>;
  showDetails: Accessor<boolean>;
  pendingApprovals: Accessor<ToolApprovalRequest[]>;
  input: Accessor<string>;
  setInput: Setter<string>;
  canSend: Accessor<boolean>;
  send: () => void;
  cancel: () => void;
  decideApproval: (request: ToolApprovalRequest, decision: ApprovalDecision) => void;
  clear: () => void;
};

export function ChatThread(props: Props) {
  return (
    <section class="thread-card chat-mainline">
      <div class="thread-header">
        <div>
          <p class="eyebrow">{copy.chat.eyebrow}</p>
          <h2>{copy.chat.title}</h2>
        </div>
        <AgentPresence state={props.agentState()} />
        <button class="icon-button" onClick={props.clear} disabled={props.busy()} title={copy.chat.clear} aria-label={copy.chat.clear}>
          <Eraser size={16} />
        </button>
      </div>

      <div class="thread-body">
        <Show when={props.messages().length > 0} fallback={<EmptyState />}>
          <For each={props.messages()}>{(message) => <MessageBubble message={message} />}</For>
        </Show>
        <Show when={props.busy()}>
          <div class="typing"><span></span><span></span><span></span></div>
        </Show>
        <ToolApprovalPanel requests={props.pendingApprovals} busy={props.busy} decide={props.decideApproval} />
      </div>

      <footer class="composer">
        <Show when={props.showDetails()}>
          <div class="telemetry">
            <span>{props.protocol()}</span>
            <span>{props.model() || copy.details.modelUnset}</span>
            <span>{props.latency() === null ? copy.details.latencyNone : copy.details.latency(props.latency()!)}</span>
            <span>{props.toolCount() ? copy.details.toolsEnabled(props.toolCount()) : copy.details.toolsDefault}</span>
            <span>{copy.details.permission(copy.settings.permissionModes[props.permissionMode()] || props.permissionMode())}</span>
          </div>
        </Show>
        <div class="composer-row">
          <textarea
            value={props.input()}
            onInput={(event) => props.setInput(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) props.send();
            }}
            aria-label={copy.chat.inputLabel}
            placeholder={copy.chat.inputPlaceholder}
          />
          <Show when={props.busy()} fallback={<button class="send-button" aria-label={copy.chat.send} title={copy.chat.inputHint} disabled={!props.canSend()} onClick={props.send}>
            <Send size={18} />
          </button>}>
            <button class="send-button" aria-label="停止当前请求" title="停止当前请求" onClick={props.cancel}><Square size={18} /></button>
          </Show>
        </div>
      </footer>
    </section>
  );
}

function MessageBubble(props: { message: ChatMessage }) {
  return (
    <article class={`message message-${props.message.role}`}>
      <div class="avatar">{props.message.role === "user" ? <MessageSquareText size={16} /> : <KevinAvatar size={28} decorative />}</div>
      <div class="bubble">
        <span>{roleLabel(props.message.role)}</span>
        <p>{props.message.content || copy.chat.pending}</p>
      </div>
    </article>
  );
}

function EmptyState() {
  return (
    <div class="empty-state">
      <KevinAvatar size={110} />
      <h3>{copy.chat.emptyTitle}</h3>
      <p>{copy.chat.emptyHint}</p>
    </div>
  );
}

function roleLabel(role: ChatMessage["role"]) {
  if (role === "user") return copy.chat.roleUser;
  if (role === "error") return copy.chat.roleError;
  return copy.chat.roleAssistant;
}
