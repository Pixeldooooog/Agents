import { splitProps, type JSX } from "solid-js";
import { KevinAvatar, stateLabels, type KevinState } from "./KevinAvatar";

export function KevinButton(props: JSX.ButtonHTMLAttributes<HTMLButtonElement> & { tone?: "primary" | "secondary" | "danger" }) {
  const [local, rest] = splitProps(props, ["tone", "class", "children"]);
  return <button type="button" {...rest} class={`k-button k-button-${local.tone || "secondary"} ${local.class || ""}`}>{local.children}</button>;
}
export function StatusBadge(props: { state: KevinState; live?: boolean }) {
  return <span class={`k-status k-status-${props.state}`} role={props.live ? "status" : undefined}>
    <span aria-hidden="true" class="k-status-dot"/>{stateLabels[props.state]}
  </span>;
}
export function KevinCard(props: { title: string; eyebrow?: string; children: JSX.Element; class?: string }) {
  return <section class={`k-card ${props.class || ""}`}><header><small>{props.eyebrow}</small><h3>{props.title}</h3></header>{props.children}</section>;
}
export function AgentPresence(props: { state: KevinState }) {
  return <div class="k-presence"><KevinAvatar state={props.state} size={44} decorative/><StatusBadge state={props.state} live/></div>;
}
