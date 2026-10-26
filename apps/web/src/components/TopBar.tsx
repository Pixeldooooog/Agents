import { Circle, Radio, Sparkles } from "lucide-solid";
import type { Accessor, Setter } from "solid-js";
import { For } from "solid-js";

type Props = {
  view: Accessor<string>;
  setView: Setter<string>;
  health: Accessor<string>;
  streaming: Accessor<boolean>;
  setStreaming: Setter<boolean>;
  checkHealth: () => void;
};

const tabs = [
  { id: "chat", label: "Chat" },
  { id: "runs", label: "Runs" },
  { id: "tasks", label: "Tasks" },
  { id: "settings", label: "Settings" },
];

export function TopBar(props: Props) {
  return (
    <header class="studio-topbar">
      <div class="brand-block">
        <div class="mark"><Sparkles size={19} /></div>
        <div>
          <h1>Kevin</h1>
          <p>Web Console</p>
        </div>
      </div>
      <div class="top-actions">
        <button class="status-pill" onClick={props.checkHealth}>
          <Circle size={10} class={`health-${props.health()}`} />
          <span>{props.health()}</span>
        </button>
        <button class="mode-toggle" classList={{ active: props.streaming() }} onClick={() => props.setStreaming(!props.streaming())}>
          <Radio size={15} />
          <span>{props.streaming() ? "Streaming" : "Single response"}</span>
        </button>
        <div class="view-tabs">
          <For each={tabs}>{(item) => (
            <button class="plain-button" classList={{ active: props.view() === item.id }} onClick={() => props.setView(item.id)}>
              <span>{item.label}</span>
            </button>
          )}</For>
        </div>
      </div>
    </header>
  );
}
