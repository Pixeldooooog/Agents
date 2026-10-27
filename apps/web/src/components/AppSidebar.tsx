import { Activity, ListTodo, MessageCircle, Plus, Settings } from "lucide-solid";
import type { Accessor, Setter } from "solid-js";
import { For } from "solid-js";
import head from "../../../../assets/kevin-head-handdrawn-v1.png";

export function AppSidebar(props: {
  view: Accessor<string>;
  setView: Setter<string>;
  busy: Accessor<boolean>;
  newConversation: () => void;
}) {
  const tabs = [
    { id: "chat", label: "对话", icon: MessageCircle },
    { id: "tasks", label: "任务", icon: ListTodo },
    { id: "runs", label: "运行记录", icon: Activity },
    { id: "settings", label: "设置", icon: Settings },
  ];
  return <aside class="app-sidebar">
    <div class="app-brand"><img src={head} alt="" /><div><strong>Kevin<span>·</span></strong><small>你的随身搭档</small></div></div>
    <button class="new-conversation" aria-label="新的对话" disabled={props.busy()} onClick={props.newConversation}><Plus size={17} /><span>新的对话</span></button>
    <nav aria-label="主导航"><For each={tabs}>{tab => <button aria-label={tab.label} aria-current={props.view() === tab.id ? "page" : undefined} onClick={() => props.setView(tab.id)}><tab.icon size={18} /><span>{tab.label}</span></button>}</For></nav>
    <div class="sidebar-note"><span class="note-stroke">一起，把事情做好。</span><small>KEVIN / PERSONAL AGENT</small></div>
  </aside>;
}
