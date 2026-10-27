import { Eraser, MessageSquareText, Send, Square } from "lucide-solid";
import type { Accessor, Setter } from "solid-js";
import { For, Show, createMemo } from "solid-js";
import type { ApprovalDecision, ChatMessage, PermissionMode, ToolApprovalRequest } from "../types/runtimeTypes";
import { ToolApprovalPanel } from "./ToolApprovalPanel";
import { copy } from "../copy";

import { KevinAvatar, type KevinState } from "./kevin/KevinAvatar";
import head from "../../../../assets/kevin-head-handdrawn-v1.png";
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
  let composerInput: HTMLTextAreaElement | undefined;
  const isWelcome = createMemo(() => !props.busy() && (props.messages().length === 0 || (props.messages().length === 1 && props.messages()[0]?.id === 1)));
  const choosePrompt = (prompt: string) => { props.setInput(prompt); composerInput?.focus(); };
  return (
    <section class="thread-card chat-mainline">
      <div class="thread-header">
        <div>
          <p class="eyebrow">KEVIN / CONVERSATION</p>
          <h2>{isWelcome() ? "从一个想法开始" : "一起进行中"}</h2>
        </div>
        <AgentPresence state={props.agentState()} />
        <button class="icon-button" onClick={props.clear} disabled={props.busy()} title={copy.chat.clear} aria-label={copy.chat.clear}>
          <Eraser size={16} />
        </button>
      </div>

      <div class="thread-body">
        <Show when={!isWelcome()} fallback={<EmptyState choosePrompt={choosePrompt} />}>
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
        <div class="composer-companion"><img src={head} alt="" /><span>{props.busy() ? "我在这里，进度随时可以查看。" : "想到了什么？慢慢说，我在。"}</span></div>
        <div class="composer-row">
          <textarea
            ref={composerInput}
            value={props.input()}
            onInput={(event) => props.setInput(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (!event.isComposing && event.key === "Enter" && (event.metaKey || event.ctrlKey) && props.canSend()) { event.preventDefault(); props.send(); }
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
        <div class="composer-caption"><span>{props.model() || "使用服务默认模型"}</span><span>⌘ / Ctrl + Enter 发送</span></div>
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

function EmptyState(props: { choosePrompt: (prompt: string) => void }) {
  const suggestions = [
    { title: "理一理思路", hint: "把模糊的想法变成下一步", prompt: "我有一个想法，想和你一起梳理。请先问我想解决什么问题。" },
    { title: "一起看代码", hint: "从理解项目开始", prompt: "请先查看当前工作空间的项目结构，解释主要模块和入口，暂时不要修改文件。" },
    { title: "拆解一件事", hint: "把目标整理成行动清单", prompt: "帮我把接下来要做的一件事拆成行动清单。请先问我目标和约束。" },
  ];
  return <div class="app-welcome">
    <div class="welcome-dog"><img src={head} alt="手绘天线小黑狗 Kevin" /><span>嘿，我在。</span></div>
    <p class="welcome-overline">A LITTLE HELP, A LITTLE EVERY DAY.</p>
    <h3>今天，我们一起做点什么？</h3>
    <p>一个问题、一个想法，或一件还没开始的事。</p>
    <div class="welcome-suggestions"><For each={suggestions}>{item => <button onClick={() => props.choosePrompt(item.prompt)}><strong>{item.title}<span>↗</span></strong><small>{item.hint}</small></button>}</For></div>
  </div>;
}

function roleLabel(role: ChatMessage["role"]) {
  if (role === "user") return copy.chat.roleUser;
  if (role === "error") return copy.chat.roleError;
  return copy.chat.roleAssistant;
}
