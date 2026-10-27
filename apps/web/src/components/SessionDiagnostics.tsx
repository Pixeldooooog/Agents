import { For, Show } from "solid-js";
import type { ActivityEvent } from "../types/chatTypes";

export function SessionDiagnostics(props: { events: ActivityEvent[] }) {
  return (
    <details class="session-diagnostics">
      <summary>本页请求日志 · {props.events.length}</summary>
      <Show when={props.events.length} fallback={<p>还没有请求日志。</p>}>
        <ol>
          <For each={props.events}>
            {(event) => (
              <li>
                <time>{event.time}</time>
                <strong>{event.title}</strong>
                <pre>{event.detail}</pre>
              </li>
            )}
          </For>
        </ol>
      </Show>
    </details>
  );
}
