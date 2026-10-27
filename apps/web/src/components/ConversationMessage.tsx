import { Check, Copy } from "lucide-solid";
import { Show, createSignal, onCleanup } from "solid-js";
import type { ChatMessage } from "../types/runtimeTypes";
import { MessageContent } from "./MessageContent";
import head from "../../../../assets/kevin-head-handdrawn-v1.png";

export function ConversationMessage(props: { message: ChatMessage }) {
  const [copyState, setCopyState] = createSignal<"idle" | "copied" | "failed">(
    "idle",
  );
  let resetTimer: ReturnType<typeof setTimeout> | undefined;
  onCleanup(() => clearTimeout(resetTimer));
  const copyMessage = async () => {
    try {
      await navigator.clipboard.writeText(props.message.content);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
    clearTimeout(resetTimer);
    resetTimer = setTimeout(() => setCopyState("idle"), 2400);
  };
  return (
    <article
      class={`conversation-message conversation-message-${props.message.role}`}
    >
      <div class="message-byline">
        <Show when={props.message.role === "assistant"}>
          <img src={head} alt="" />
        </Show>
        <strong>
          {props.message.role === "user"
            ? "你"
            : props.message.role === "error"
              ? "遇到一点问题"
              : "Kevin"}
        </strong>
        <Show when={props.message.role === "assistant"}>
          <span>你的搭档</span>
        </Show>
      </div>
      <Show
        when={props.message.role === "assistant"}
        fallback={<p class="message-plain">{props.message.content}</p>}
      >
        <MessageContent content={props.message.content || "正在整理…"} />
        <Show when={props.message.content}>
          <div class="message-actions">
            <button onClick={() => void copyMessage()} aria-label="复制回复">
              <Show
                when={copyState() === "copied"}
                fallback={<Copy size={13} />}
              >
                <Check size={13} />
              </Show>
              <span>
                {copyState() === "copied"
                  ? "已复制"
                  : copyState() === "failed"
                    ? "复制失败，请重试"
                    : "复制"}
              </span>
            </button>
            <span role="status">
              {copyState() === "copied"
                ? "回复已复制"
                : copyState() === "failed"
                  ? "无法访问剪贴板"
                  : ""}
            </span>
          </div>
        </Show>
      </Show>
    </article>
  );
}
