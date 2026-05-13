import { AlertTriangle, CheckCircle2, FileText, FolderOpen, GitBranch, Globe2, Search, TerminalSquare } from "lucide-solid";
import type { JSX } from "solid-js";
import { For, Match, Show, Switch, createMemo } from "solid-js";
import { scriptForOperation, type StageScript } from "../runtime/operationStageScript";
import type { OperationEvent, OperationSceneKind } from "../types";

const meta: Record<OperationSceneKind, { label: string; icon: () => JSX.Element }> = {
  workspace: { label: "Workspace", icon: () => <FolderOpen size={15} /> },
  edit: { label: "Editor", icon: () => <FileText size={15} /> },
  web: { label: "Web search", icon: () => <Globe2 size={15} /> },
  browser: { label: "Browser", icon: () => <Globe2 size={15} /> },
  terminal: { label: "Terminal", icon: () => <TerminalSquare size={15} /> },
  git: { label: "Git", icon: () => <GitBranch size={15} /> },
  document: { label: "Documents", icon: () => <FileText size={15} /> },
  summary: { label: "Summary", icon: () => <CheckCircle2 size={15} /> },
};

export function OperationScene(props: { event: OperationEvent }) {
  const script = createMemo(() => scriptForOperation(props.event));
  return (
    <div class={`scene-canvas scene-${props.event.scene}`} data-phase={props.event.phase}>
      <DesktopBackdrop event={props.event} script={script()} />
      <ProcessStrip script={script()} />
      <AutomationTrace script={script()} />
      <Switch fallback={<WorkspaceScene event={props.event} />}>
        <Match when={props.event.scene === "web" || props.event.scene === "browser"}><WebScene event={props.event} /></Match>
        <Match when={props.event.scene === "terminal" || props.event.scene === "git"}><TerminalScene event={props.event} /></Match>
        <Match when={props.event.scene === "document"}><DocumentScene event={props.event} /></Match>
        <Match when={props.event.scene === "edit"}><EditScene event={props.event} /></Match>
        <Match when={props.event.scene === "summary"}><SummaryScene event={props.event} /></Match>
      </Switch>
      <EvidenceTray script={script()} />
    </div>
  );
}

export function sceneLabel(scene: OperationSceneKind) {
  return meta[scene].label;
}

export function SceneIcon(props: { scene: OperationSceneKind }) {
  return meta[props.scene].icon();
}

export function StatusMark(props: { status: string }) {
  if (props.status === "error") return <AlertTriangle class="status-mark error" size={15} />;
  if (props.status === "done") return <CheckCircle2 class="status-mark done" size={15} />;
  return <span class="status-mark running" />;
}

function DesktopBackdrop(props: { event: OperationEvent; script: StageScript }) {
  return (
    <div class="desktop-backdrop">
      <div class="focus-beam" />
      <div class="stage-command-line">{props.script.appLabel} · {props.script.command}</div>
      <div class="desktop-dock">
        <span classList={{ active: props.event.scene === "workspace" || props.event.scene === "edit" }}><FolderOpen size={17} /></span>
        <span classList={{ active: props.event.scene === "web" || props.event.scene === "browser" }}><Globe2 size={17} /></span>
        <span classList={{ active: props.event.scene === "terminal" || props.event.scene === "git" }}><TerminalSquare size={17} /></span>
        <span classList={{ active: props.event.scene === "document" }}><FileText size={17} /></span>
      </div>
    </div>
  );
}

function ProcessStrip(props: { script: StageScript }) {
  return (
    <div class="process-strip">
      <For each={props.script.steps}>{(step) => (
        <span classList={{ active: step.status === "active", done: step.status === "done", error: step.status === "error" }}>{step.label}</span>
      )}</For>
    </div>
  );
}

function AutomationTrace(props: { script: StageScript }) {
  return (
    <div class="automation-trace">
      <For each={props.script.steps}>{(step) => (
        <article class={`automation-step ${step.status}`}>
          <span class="step-led" />
          <div><strong>{step.label}</strong><small>{step.detail}</small></div>
        </article>
      )}</For>
    </div>
  );
}

function EvidenceTray(props: { script: StageScript }) {
  return (
    <Show when={props.script.evidence.length > 0}>
      <div class="evidence-tray">
        <For each={props.script.evidence}>{(item) => (
          <article class={`evidence-chip ${item.tone || ""}`}><strong>{item.label}</strong><span>{item.value}</span></article>
        )}</For>
      </div>
    </Show>
  );
}

function WorkspaceScene(props: { event: OperationEvent }) {
  const files = () => props.event.files?.length ? props.event.files : [{ path: props.event.target || "workspace", status: "open" }];
  return (
    <>
      <StageWindow className="finder-window" title="Workspace" subtitle={props.event.target || "project files"}>
        <div class="finder-grid">
          <div class="finder-sidebar"><span>Project</span><span>apps</span><span>src</span><span>docs</span></div>
          <div class="file-list-mini">
            <For each={files()}>{(file, index) => <FileRow active={index() === 0} label={file.path} meta={file.status || file.kind || "ready"} />}</For>
          </div>
        </div>
      </StageWindow>
      <StageWindow className="editor-window-mini" title="Preview" subtitle={props.event.toolName}>
        <CodePreview event={props.event} />
      </StageWindow>
    </>
  );
}

function EditScene(props: { event: OperationEvent }) {
  return (
    <StageWindow className="editor-window-large" title="Editor" subtitle={props.event.target || props.event.toolName}>
      <CodePreview event={props.event} mode="edit" />
    </StageWindow>
  );
}

function WebScene(props: { event: OperationEvent }) {
  return (
    <StageWindow className="browser-window-mini" title="Browser" subtitle={props.event.toolName}>
      <div class="browser-toolbar"><Search size={14} /><span>{props.event.target || "search query"}</span></div>
      <div class="browser-results">
        <Show when={(props.event.sources?.length || 0) > 0} fallback={<SourceCard active title="Searching" detail={props.event.detail || "Opening sources"} />}>
          <For each={props.event.sources || []}>{(source, index) => <SourceCard active={index() === 0} title={source.title} detail={source.domain || source.url || source.content || "source"} />}</For>
        </Show>
      </div>
    </StageWindow>
  );
}

function TerminalScene(props: { event: OperationEvent }) {
  const resultText = () => {
    if (typeof props.event.resultPreview === "string") return props.event.resultPreview;
    if (!props.event.resultPreview) return "";
    return JSON.stringify(props.event.resultPreview, null, 2);
  };
  return (
    <StageWindow className="terminal-window-mini" title={props.event.scene === "git" ? "Git" : "Terminal"} subtitle={props.event.toolName}>
      <pre class="terminal-lines"><span>$ </span>{props.event.target || props.event.detail || props.event.toolName}
{"\n"}{props.event.phase === "opening" ? "running..." : props.event.phase === "error" ? "error: command failed" : "completed"}
{"\n"}{resultText().slice(0, 360)}</pre>
    </StageWindow>
  );
}

function DocumentScene(props: { event: OperationEvent }) {
  return (
    <StageWindow className="document-window-mini" title="Reader" subtitle={props.event.target || props.event.toolName}>
      <h3>{props.event.target || "Context document"}</h3>
      <p>{props.event.detail || "Reading local context, skill guidance, prompts, or MCP resources."}</p>
      <ul><li>Open source</li><li>Extract constraints</li><li>Return context to chat</li></ul>
    </StageWindow>
  );
}

function SummaryScene(props: { event: OperationEvent }) {
  return (
    <StageWindow className="summary-window-mini" title="Run summary" subtitle="windows closed">
      <div class="summary-grid">
        <SourceCard title="Operations" detail={props.event.detail || "Workspace activity completed"} />
        <SourceCard title="Artifacts" detail={`${props.event.artifacts?.length || 0} captured`} />
        <SourceCard title="Answer" detail="Final response continues in the conversation" />
      </div>
    </StageWindow>
  );
}

function StageWindow(props: { className: string; title: string; subtitle: string; children: JSX.Element }) {
  return (
    <section class={`stage-window ${props.className}`}>
      <header class="stage-window-title">
        <div><strong>{props.title}</strong><span>{props.subtitle}</span></div>
        <div class="window-dots"><i /><i /><i /></div>
      </header>
      <div class="stage-window-body">{props.children}</div>
    </section>
  );
}

function CodePreview(props: { event: OperationEvent; mode?: "edit" }) {
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

function FileRow(props: { label: string; meta?: string; active?: boolean }) {
  return <div class="file-row-mini" classList={{ active: props.active }}><span>{props.label}</span><small>{props.meta}</small></div>;
}

function SourceCard(props: { title: string; detail: string; active?: boolean }) {
  return <article class="source-card-mini" classList={{ active: props.active }}><strong>{props.title}</strong><p>{props.detail}</p></article>;
}
