import { Eraser, MessageSquareText, Send } from "lucide-solid";
import type { Accessor, Setter } from "solid-js";
import { For, Show } from "solid-js";
import type { ApprovalDecision, ChatMessage, PermissionMode, ToolApprovalRequest } from "../types/runtimeTypes";
import { ToolApprovalPanel } from "./ToolApprovalPanel";

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
  pendingApprovals: Accessor<ToolApprovalRequest[]>;
  input: Accessor<string>;
  setInput: Setter<string>;
  canSend: Accessor<boolean>;
  send: () => void;
  decideApproval: (request: ToolApprovalRequest, decision: ApprovalDecision) => void;
  clear: () => void;
};

export function ChatThread(props: Props) {
  return (
    <section class="thread-card chat-mainline">
      <div class="thread-header">
        <div>
          <p class="eyebrow">Conversation</p>
          <h2>Work with Kevin</h2>
        </div>
        <AgentPresence state={props.agentState()} />
        <button class="icon-button" onClick={props.clear} title="Clear conversation">
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
        <div class="telemetry">
          <span>{props.protocol()}</span>
          <span>{props.model() || "model not set"}</span>
          <span>{props.latency() === null ? "no latency yet" : `${props.latency()} ms`}</span>
          <span>{props.toolCount() ? `${props.toolCount()} enabled tools` : "default tool set"}</span>
          <span>{props.permissionMode()} permissions</span>
        </div>
        <div class="composer-row">
          <textarea
            value={props.input()}
            onInput={(event) => props.setInput(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) props.send();
            }}
            aria-label="Message Kevin"
            placeholder="What shall we work on?"
          />
          <button class="send-button" aria-label="Send message" disabled={!props.canSend()} onClick={props.send}>
            <Send size={18} />
          </button>
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
        <span>{props.message.role}</span>
        <p>{props.message.content || "..."}</p>
      </div>
    </article>
  );
}

function EmptyState() {
  return (
    <div class="empty-state">
      <KevinAvatar size={110} />
      <h3>Ready</h3>
      <p>Send a task to start a run.</p>
    </div>
  );
}
