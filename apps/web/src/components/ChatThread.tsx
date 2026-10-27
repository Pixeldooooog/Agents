import { ArrowDown, Send, Square } from "lucide-solid";
import type { Accessor, Setter } from "solid-js";
import {
  For,
  Show,
  createMemo,
  createSignal,
  createEffect,
  onMount,
  onCleanup,
} from "solid-js";
import type {
  ApprovalDecision,
  ActivityEvent,
  ChatMessage,
  PermissionMode,
  ToolApprovalRequest,
} from "../types/runtimeTypes";
import { SessionDiagnostics } from "./SessionDiagnostics";
import { ToolApprovalPanel } from "./ToolApprovalPanel";
import { copy } from "../copy";

import { type KevinState } from "./kevin/KevinAvatar";
import { ChatWelcome } from "./ChatWelcome";
import { ConversationMessage } from "./ConversationMessage";
import { AgentPresence } from "./kevin/Primitives";

type Props = {
  agentState: Accessor<KevinState>;
  activity: Accessor<ActivityEvent[]>;
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
  decideApproval: (
    request: ToolApprovalRequest,
    decision: ApprovalDecision,
  ) => void;
  openSettings: () => void;
};

export function ChatThread(props: Props) {
  let composerInput: HTMLTextAreaElement | undefined;
  let threadBody: HTMLDivElement | undefined;
  let messageList: HTMLDivElement | undefined;
  const [following, setFollowing] = createSignal(true);
  const scrollToLatest = () => {
    if (threadBody) threadBody.scrollTop = threadBody.scrollHeight;
    setFollowing(true);
  };
  onMount(() => {
    const observer = new ResizeObserver(() => {
      if (following() && threadBody)
        threadBody.scrollTop = threadBody.scrollHeight;
    });
    if (messageList) observer.observe(messageList);
    onCleanup(() => observer.disconnect());
  });
  createEffect(() => {
    props.input();
    if (composerInput) {
      composerInput.style.height = "auto";
      composerInput.style.height = `${Math.min(composerInput.scrollHeight, 200)}px`;
    }
  });
  const conversationTitle = createMemo(
    () =>
      props.messages().find((message) => message.role === "user")?.content ||
      "新的对话",
  );
  const isWelcome = createMemo(
    () =>
      !props.busy() &&
      (props.messages().length === 0 ||
        (props.messages().length === 1 && props.messages()[0]?.id === 1)),
  );
  const choosePrompt = (prompt: string) => {
    props.setInput(prompt);
    composerInput?.focus();
  };
  return (
    <section class="thread-card chat-mainline">
      <div class="thread-header">
        <div class="thread-heading">
          <p class="eyebrow">与你，一起</p>
          <h2 title={conversationTitle()}>{conversationTitle()}</h2>
        </div>
        <AgentPresence state={props.agentState()} />
      </div>
      <div class="conversation-scroll">
        <div
          class="thread-body"
          ref={threadBody}
          onScroll={() => {
            if (threadBody)
              setFollowing(
                threadBody.scrollHeight -
                  threadBody.scrollTop -
                  threadBody.clientHeight <
                  70,
              );
          }}
        >
          <div class="message-list" ref={messageList}>
            <Show
              when={!isWelcome()}
              fallback={<ChatWelcome choosePrompt={choosePrompt} />}
            >
              <For
                each={props.messages().filter((message) => message.id !== 1)}
              >
                {(message) => <ConversationMessage message={message} />}
              </For>
            </Show>
            <Show when={props.busy()}>
              <div class="thinking-line" role="status">
                <div class="typing">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
                <span>
                  {props.agentState() === "working"
                    ? "正在处理，步骤会记在工作过程里"
                    : "正在想一想…"}
                </span>
              </div>
            </Show>
            <ToolApprovalPanel
              requests={props.pendingApprovals}
              busy={props.busy}
              decide={props.decideApproval}
            />
          </div>
        </div>
        <Show when={!following()}>
          <button class="latest-message" onClick={scrollToLatest}>
            <ArrowDown size={14} />
            回到最新
          </button>
        </Show>
      </div>
      <footer class="composer">
        <Show when={props.showDetails()}>
          <SessionDiagnostics events={props.activity()} />
          <div class="telemetry">
            <span>{props.protocol()}</span>
            <span>{props.model() || copy.details.modelUnset}</span>
            <span>
              {props.latency() === null
                ? copy.details.latencyNone
                : copy.details.latency(props.latency()!)}
            </span>
            <span>
              {props.toolCount()
                ? copy.details.toolsEnabled(props.toolCount())
                : copy.details.toolsDefault}
            </span>
            <span>
              {copy.details.permission(
                copy.settings.permissionModes[props.permissionMode()] ||
                  props.permissionMode(),
              )}
            </span>
          </div>
        </Show>
        <div class="composer-companion">
          <span>
            {props.pendingApprovals().length
              ? "下一步，需要你点个头。"
              : props.busy()
                ? "我在处理，你可以随时叫停。"
                : "留个想法，我们接着往下。"}
          </span>
        </div>
        <div class="composer-row">
          <textarea
            ref={composerInput}
            value={props.input()}
            onInput={(event) => props.setInput(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (
                !event.isComposing &&
                event.key === "Enter" &&
                (event.metaKey || event.ctrlKey) &&
                props.canSend()
              ) {
                event.preventDefault();
                props.send();
              }
            }}
            aria-label={copy.chat.inputLabel}
            placeholder={copy.chat.inputPlaceholder}
          />
          <Show
            when={props.busy()}
            fallback={
              <button
                class="send-button"
                aria-label={copy.chat.send}
                title={copy.chat.inputHint}
                disabled={!props.canSend()}
                onClick={props.send}
              >
                <Send size={18} />
              </button>
            }
          >
            <button
              class="send-button"
              aria-label="停止当前请求"
              title="停止当前请求"
              onClick={props.cancel}
            >
              <Square size={18} />
            </button>
          </Show>
        </div>
        <div class="composer-caption">
          <button onClick={props.openSettings} title="配置模型与权限">
            {props.model() || "默认模型"}
            <span>
              {" "}
              · {copy.settings.permissionModes[props.permissionMode()]}
            </span>
          </button>
          <span>⌘ / Ctrl + Enter 发送</span>
        </div>
      </footer>
    </section>
  );
}
