import { For, Show, createMemo, createSignal } from "solid-js";
import { KevinAvatar, type KevinState } from "./KevinAvatar";
import { KevinButton, StatusBadge } from "./Primitives";
import "../../styles/work-canvas.css";

type Phase = "understand" | "draft" | "review" | "done";
const phases: { id: Phase; label: string; detail: string }[] = [
  { id: "understand", label: "理解目标", detail: "读材料，明确边界" },
  { id: "draft", label: "形成草稿", detail: "让想法变成可见成果" },
  { id: "review", label: "等你确认", detail: "关键决定交给你" },
  { id: "done", label: "收好成果", detail: "带着结果离开" },
];
const sources = [
  { name: "README.md", kind: "项目说明", excerpt: "示例摘录：Kevin 是一个面向代码、资料与日常工作的个人智能体。当前为开发预览。" },
  { name: "package.json", kind: "启动入口", excerpt: "示例摘录：运行环境为 Bun。Web、终端与 Host 作为独立入口，启动步骤需清楚区分。" },
  { name: "support-matrix.md", kind: "能力边界", excerpt: "示例摘录：保留开发预览说明；没有验收的能力不能描述为已经交付。" },
];

/** Local interaction prototype. No API requests or filesystem mutations. */
export function WorkCanvas() {
  const [phase, setPhase] = createSignal<Phase>("review");
  const [source, setSource] = createSignal<number | null>(null);
  const [editing, setEditing] = createSignal(false);
  const [title, setTitle] = createSignal("一个入口，开始和 Kevin 工作。");
  const [intro, setIntro] = createSignal("把代码、资料与日常工作交给 Kevin。你可以查看每一步，在需要时给出方向，并带走清楚的结果。");
  const [instruction, setInstruction] = createSignal("");
  const [notes, setNotes] = createSignal<string[]>([]);
  const [history, setHistory] = createSignal(false);
  const [notice, setNotice] = createSignal("");
  const state = createMemo<KevinState>(() => ({ understand: "thinking", draft: "working", review: "approval", done: "done" } as const)[phase()]);
  const currentIndex = () => phases.findIndex(p => p.id === phase());
  const explanation = () => ({ understand: "先弄清楚要做什么，再开始动手。", draft: "我在整理这份草稿。你可以随时补充方向。", review: "草稿在这里。要不要按这个方向继续？", done: "这一版已在预览中确认，成果留在桌上。" })[phase()];
  const changePhase = (p: Phase) => { setPhase(p); setNotice(""); setEditing(false); };
  const addNote = () => {
    const note = instruction().trim();
    if (!note) return;
    setNotes(items => [...items, note]); setInstruction(""); setPhase("draft");
    setNotice("补充已放入任务约束（本地演示）；尚未自动改写草稿。");
  };
  const reset = () => {
    setPhase("review"); setSource(null); setEditing(false); setNotes([]); setHistory(false); setNotice("");
    setTitle("一个入口，开始和 Kevin 工作。"); setIntro("把代码、资料与日常工作交给 Kevin。你可以查看每一步，在需要时给出方向，并带走清楚的结果。"); setInstruction("");
  };
  return <section class="work-canvas" aria-label="Kevin 成果工作台">
    <header class="canvas-topline"><span><span class="canvas-live-dot"/> 我的桌面 <span class="canvas-slash">/</span> 项目说明改版</span><div><span class="prototype-label">交互样机 · 示例数据</span><button class="text-action" onClick={reset}>重置体验 ↺</button></div></header>
    <section class="canvas-brief"><div><p class="canvas-overline">TODAY'S INTENTION</p><h2>让第一次遇见 Kevin 的人，<br/>知道从哪里开始。</h2><div class="brief-tags"><span>README 改版</span><span>保留能力边界</span><span>先看草稿，再决定</span></div></div><div class="canvas-companion"><KevinAvatar state={state()} size={104}/><div><StatusBadge state={state()} live/><p>{explanation()}</p></div></div></section>
    <nav class="canvas-path" aria-label="任务阶段预览"><For each={phases}>{(p,i) => <button aria-current={phase()===p.id ? "step" : undefined} onClick={()=>changePhase(p.id)}><span class="path-number">{i()<currentIndex()?"✓":`0${i()+1}`}</span><span>{p.label}</span><small>{p.detail}</small></button>}</For></nav>
    <div class="canvas-spread">
      <aside class="canvas-materials"><p class="canvas-overline">ON THE DESK</p><h3>带着这些工作</h3><div class="source-stack"><For each={sources}>{(item,i) => <button class="source-slip" aria-expanded={source()===i()} onClick={()=>setSource(source()===i()?null:i())}><span class="source-fold" aria-hidden="true">↗</span><small>0{i()+1} / {item.kind}</small><strong>{item.name}</strong><span>查看依据</span></button>}</For></div><Show when={source()!==null}><div class="source-excerpt" role="region" aria-label="材料摘录"><strong>{sources[source()!].name}</strong><p>{sources[source()!].excerpt}</p><button class="text-action" onClick={()=>setSource(null)}>收起摘录</button></div></Show><div class="margin-note">先理解你的材料，<br/>再形成自己的判断。<span aria-hidden="true">⤴</span></div></aside>
      <div class="canvas-artifact-area"><div class="artifact-caption"><span><span class="artifact-dot"/> README / 工作草稿</span><span>01 · 可直接编辑</span></div>
        <article class="artifact-paper" aria-label="README 草稿"><div class="paper-corner"/><header><span>KEVIN / GETTING STARTED</span><button class="text-action" onClick={()=>setEditing(!editing())} disabled={phase()==="done"}>{editing()?"收起编辑":"直接修改 ✎"}</button></header>
          <Show when={phase()!=="understand"} fallback={<div class="understand-sheet"><p class="paper-eyebrow">先对齐方向</p><h3>一份 README，<br/>回答三个问题。</h3><ol><li>Kevin 能帮我做什么？</li><li>我该如何启动第一次任务？</li><li>哪些能力还在开发中？</li></ol><p>三份示例材料已放在左侧。点击卡片查看依据，或补充你希望强调的内容。</p><KevinButton onClick={()=>changePhase("draft")}>按这个方向起草 →</KevinButton></div>}>
            <p class="paper-eyebrow">HELLO, KEVIN.</p><Show when={editing()} fallback={<><h3>{title()}</h3><p class="paper-intro">{intro()}</p></>}><div class="paper-editor"><label for="canvas-title">草稿标题</label><input id="canvas-title" value={title()} onInput={e=>setTitle(e.currentTarget.value)}/><label for="canvas-intro">介绍文字</label><textarea id="canvas-intro" value={intro()} onInput={e=>setIntro(e.currentTarget.value)}/><p>本地即时预览，不会写入仓库文件。</p></div></Show>
            <div class="paper-rule"/><div class="paper-section"><span>01</span><div><h4>从一件小事开始</h4><p>打开工作区，配置模型，然后交给 Kevin 一个具体目标。</p></div></div><div class="paper-section"><span>02</span><div><h4>看过程，也看结果</h4><p>查看工具调用与变更，在重要操作前做决定。</p></div></div><div class="paper-boundary"><span>开发预览</span><p>明确已支持的能力与限制，保留安装要求和支持矩阵。</p></div>
            <footer><span>{phase()==="done"?"✓ 本地预览已确认":"草稿 · 尚未写入文件"}</span><span>README.md</span></footer>
          </Show>
        </article><div class="artifact-shadow"/><p class="artifact-footnote">成果一直在这里，讨论不会把它冲走。</p>
      </div>
      <aside class="canvas-decisions"><p class="canvas-overline">YOUR PART</p>
        <Show when={phase()==="review"} fallback={<div class="decision-note"><span class="decision-symbol" aria-hidden="true">{phase()==="done"?"✓":"…"}</span><h3>{phase()==="done"?"这一版，收好了。":"你可以先看看。"}</h3><p>{phase()==="done"?"这是本地原型中的确认。没有修改或推送真实文件。":"随时打开材料、编辑草稿，或在下方补充要求。"}</p><Show when={phase()==="draft"}><KevinButton tone="primary" onClick={()=>changePhase("review")}>预览待确认 →</KevinButton></Show><Show when={phase()==="done"}><KevinButton onClick={()=>changePhase("draft")}>再改一版</KevinButton></Show></div>}>
          <div class="decision-note"><span class="decision-symbol" aria-hidden="true">?</span><h3>这个方向，<br/>可以继续吗？</h3><p>将以当前草稿为基础更新 1 个文件。正式产品中，这里会展示真实差异与影响范围。</p><div class="decision-scope"><span>README.md</span><span>仅本地演示</span></div><KevinButton tone="primary" onClick={()=>{changePhase("done");setNotice("已确认当前草稿（仅本地预览，未写入文件）。");}}>这个方向可以 ↗</KevinButton><button class="text-action" onClick={()=>{changePhase("draft");setEditing(true);setNotice("已退回草稿，你可以直接修改内容。");}}>我想调整一下</button></div>
        </Show>
        <div class="constraint-note"><h4>一直记着的要求</h4><ul><li>新人能快速上手</li><li>不夸大当前能力</li><For each={notes()}>{note=><li>{note}</li>}</For></ul></div>
      </aside>
    </div>
    <div class="canvas-bottom"><form class="direction-bar" onSubmit={e=>{e.preventDefault();addNote();}}><KevinAvatar state={instruction()?"listening":state()} size={52} decorative/><div><label for="canvas-direction">随时补一句，工作就有了新方向。</label><input id="canvas-direction" placeholder="比如：安装步骤放到更前面，语气再轻松一点…" value={instruction()} onInput={e=>setInstruction(e.currentTarget.value)}/></div><button class="direction-send" type="submit" aria-label="补充要求" disabled={!instruction().trim()}>↗</button></form>
      <div class="canvas-underbar"><button class="text-action" aria-expanded={history()} onClick={()=>setHistory(!history())}>补充与讨论 <span>{notes().length}</span> {history()?"↑":"↓"}</button><p>原型内交互，不调用模型、不修改文件。</p></div>
      <Show when={notice()}><p class="canvas-notice" role="status">{notice()}</p></Show>
      <Show when={history()}><section class="canvas-journal" aria-label="补充与讨论"><h3>思路留在这里。</h3><p><strong>最初的目标</strong>让新人更容易了解和使用 Kevin。</p><Show when={notes().length} fallback={<p>还没有补充。你的要求会同时留在这里与任务约束中。</p>}><For each={notes()}>{(note,i)=><p><strong>补充 {i()+1}</strong>{note}</p>}</For></Show></section></Show>
    </div>
  </section>;
}

export function WorkCanvasPreview() {
  const [dark, setDark] = createSignal(false);
  return <div class="design-studio canvas-page" data-theme={dark()?"dark":"light"}><header class="canvas-page-header"><a class="design-brand" href="?design"><KevinAvatar size={42} decorative/><span>kevin.</span></a><span>少一点来回，多一点成果。</span><div><a href="?design#workspace">组件规范</a><KevinButton onClick={()=>setDark(!dark())}>{dark()?"浅色纸面":"深色纸面"}</KevinButton></div></header><main><WorkCanvas/></main></div>;
}
