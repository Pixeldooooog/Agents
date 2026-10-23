import { FileText, FolderOpen, Globe2, TerminalSquare } from "lucide-solid";
import type { JSX } from "solid-js";
import { For, Show } from "solid-js";
import type { StageScript } from "../runtime/operationStageScript";
import { surfaceForScene } from "../runtime/operationSurfaces";
import type { OperationEvent } from "../types/runtimeTypes";

export function DesktopBackdrop(props: { event: OperationEvent; script: StageScript }) {
  const surface = () => surfaceForScene(props.event.scene);
  return (
    <div class="desktop-backdrop">
      <div class="focus-beam" />
      <div class="stage-command-line">
        {props.script.appLabel} · {props.script.command}
      </div>
      <div class="desktop-dock">
        <span classList={{ active: surface() === "finder" || surface() === "editor" }}>
          <FolderOpen size={17} />
        </span>
        <span classList={{ active: surface() === "browser" }}>
          <Globe2 size={17} />
        </span>
        <span classList={{ active: surface() === "terminal" }}>
          <TerminalSquare size={17} />
        </span>
        <span classList={{ active: surface() === "reader" }}>
          <FileText size={17} />
        </span>
      </div>
    </div>
  );
}

export function AutomationTrace(props: { script: StageScript }) {
  return (
    <div class="automation-trace">
      <For each={props.script.steps}>
        {(step) => (
          <article class={`automation-step ${step.status}`}>
            <span class="step-led" />
            <div>
              <strong>{step.label}</strong>
              <small>{step.detail}</small>
            </div>
          </article>
        )}
      </For>
    </div>
  );
}

export function EvidenceTray(props: { script: StageScript }) {
  return (
    <Show when={props.script.evidence.length > 0}>
      <div class="evidence-tray">
        <For each={props.script.evidence}>
          {(item) => (
            <article class={`evidence-chip ${item.tone || ""}`}>
              <strong>{item.label}</strong>
              <span>{item.value}</span>
            </article>
          )}
        </For>
      </div>
    </Show>
  );
}

export function StageWindow(props: { className: string; title: string; subtitle: string; children: JSX.Element }) {
  return (
    <section class={`stage-window ${props.className}`}>
      <header class="stage-window-title">
        <div>
          <strong>{props.title}</strong>
          <span>{props.subtitle}</span>
        </div>
        <div class="window-dots">
          <i />
          <i />
          <i />
        </div>
      </header>
      <div class="stage-window-body">{props.children}</div>
    </section>
  );
}

export function CodePreview(props: { event: OperationEvent; mode?: "edit" }) {
  const diff = () => {
    if (!props.event.diffPreview) return "";
    const text = typeof props.event.diffPreview === "string" ? props.event.diffPreview : JSON.stringify(props.event.diffPreview, null, 2);
    return text.slice(0, 900);
  };
  return (
    <pre class="code-preview"><span class="line-no">01</span> tool: {props.event.toolName}
{"\n"}<span class="line-no">02</span> target: {props.event.target || "workspace"}
{"\n"}<span class={props.mode === "edit" ? "code-add-line" : ""}><span class="line-no">03</span> {props.mode === "edit" ? "+ " : ""}{props.event.detail || "Reading workspace context"}</span>
{"\n"}{diff()}</pre>
  );
}

export function FileRow(props: { label: string; meta?: string; active?: boolean }) {
  return (
    <div class="file-row-mini" classList={{ active: props.active }}>
      <span>{props.label}</span>
      <small>{props.meta}</small>
    </div>
  );
}

export function SourceCard(props: { title: string; detail: string; active?: boolean }) {
  return (
    <article class="source-card-mini" classList={{ active: props.active }}>
      <strong>{props.title}</strong>
      <p>{props.detail}</p>
    </article>
  );
}
