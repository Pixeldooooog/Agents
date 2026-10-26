import { CloudOff } from "lucide-solid";
import type { Accessor, Setter } from "solid-js";
import { For, Show } from "solid-js";

import { copy } from "../copy";
import { KevinAvatar } from "./kevin/KevinAvatar";

type Props = {
  view: Accessor<string>;
  setView: Setter<string>;
  health: Accessor<string>;
  checkHealth: () => void;
};

const tabs = [
  { id: "chat", label: copy.nav.chat },
  { id: "runs", label: copy.nav.runs },
  { id: "tasks", label: copy.nav.tasks },
  { id: "settings", label: copy.nav.settings },
];

export function TopBar(props: Props) {
  const connectionProblem = () => (props.health() === "offline" || props.health() === "degraded" ? props.health() : "");

  return (
    <>
      <header class="studio-topbar">
        <div class="brand-block">
          <div class="mark"><KevinAvatar size={48} decorative /></div>
          <div>
            <h1>{copy.brand.name}</h1>
            <p>{copy.brand.tagline}</p>
          </div>
        </div>
        <nav class="view-tabs" aria-label={copy.nav.label}>
          <For each={tabs}>{(item) => (
            <button
              class="plain-button"
              classList={{ active: props.view() === item.id }}
              aria-current={props.view() === item.id ? "page" : undefined}
              onClick={() => props.setView(item.id)}
            >
              <span>{item.label}</span>
            </button>
          )}</For>
        </nav>
      </header>
      <Show when={connectionProblem()}>
        <div class="connection-notice" role="status">
          <CloudOff size={15} />
          <span>{connectionProblem() === "offline" ? copy.connection.offline : copy.connection.degraded}</span>
          <button class="plain-button" onClick={props.checkHealth}>{copy.connection.retry}</button>
        </div>
      </Show>
    </>
  );
}
