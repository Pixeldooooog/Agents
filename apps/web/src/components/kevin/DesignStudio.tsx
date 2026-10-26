import { For, createSignal } from "solid-js";
import { KevinAvatar, kevinStates, stateLabels, type KevinState } from "./KevinAvatar";
import { WorkCanvas } from "./WorkCanvas";
import { KevinButton, KevinCard, StatusBadge } from "./Primitives";

const descriptions: Record<KevinState, string> = {
  ready: "放松垂耳，安静等候", listening: "短折耳抬起，侧头倾听", thinking: "耳朵收拢，天线轻摆", working: "耳朵向后，天线有节奏亮起", done: "眯眼笑，耳朵轻弹一次", approval: "单耳半抬，等你决定", error: "停止动作，明确提示问题"
};
export function DesignStudio() {
  const [state, setState] = createSignal<KevinState>("ready");
  const [dark, setDark] = createSignal(false);
  return <div class="design-studio" data-theme={dark() ? "dark" : "light"}>
    <header class="design-masthead"><a href="?" class="design-brand"><KevinAvatar size={48} decorative/><span>kevin<span class="brand-dot">.</span></span></a>
      <span class="design-edition">THE COMPANION NOTEBOOK / 01</span>
      <KevinButton onClick={() => setDark(!dark())}>{dark() ? "浅色纸面" : "深色纸面"}</KevinButton>
    </header>
    <main class="design-content">
      <section class="design-hero"><div><p class="k-kicker">KEVIN DESIGN LANGUAGE</p><h1>认真做事，<br/>也有一点可爱。</h1><p class="design-lede">一只会倾听的天线狗，一个清晰、安静的工作空间。<br/>把复杂留给能力，把简单留给你。</p><div class="design-notes"><span>黑墨线条</span><span>温暖纸面</span><span>琥珀信号</span></div></div>
        <div class="hero-dog"><KevinAvatar state={state()} size={230}/><StatusBadge state={state()}/><p>{descriptions[state()]}</p></div>
      </section>
      <section class="design-section"><div class="section-heading"><div><p class="k-kicker">01 / EXPRESSION</p><h2>表情，是有意义的反馈。</h2></div><span>点击切换 · 支持减少动态效果</span></div>
        <div class="state-grid"><For each={kevinStates}>{(s) => <button class="state-tile" aria-pressed={state() === s} onClick={() => setState(s)}><KevinAvatar state={s} size={100} decorative animated={state() === s}/><strong>{stateLabels[s]}</strong><small>{descriptions[s]}</small></button>}</For></div>
        <p class="design-caption">执行态保留双眼，用后收的耳朵、天线脉冲与“执行中”文字共同表达。倾听是视觉预留状态，当前产品未接入语音输入。</p>
      </section>
      <section class="design-section" id="workspace"><div class="section-heading"><div><p class="k-kicker">02 / LIVING WORKSPACE</p><h2>让成果成为对话的中心。</h2></div><a class="text-action" href="?design=workspace">全屏体验新工作台 ↗</a></div><WorkCanvas/></section>
      <section class="design-section"><div class="section-heading"><div><p class="k-kicker">03 / COMPONENTS</p><h2>一套小而完整的日常组件。</h2></div></div><div class="component-grid">
      <KevinCard eyebrow="ACTION" title="清楚的动作层级"><div class="button-row"><KevinButton tone="primary" onClick={()=>{setState("working");}}>开始工作</KevinButton><KevinButton onClick={()=>setState("approval")}>稍等一下</KevinButton><KevinButton tone="danger" onClick={()=>setState("error")}>错误示例</KevinButton><KevinButton disabled>暂不可用</KevinButton></div><p>实心主操作、描边次操作，危险动作保留明确文字。</p></KevinCard>
      <KevinCard eyebrow="FEEDBACK" title="状态不只靠颜色"><div class="badge-row"><For each={kevinStates}>{s=><StatusBadge state={s}/>}</For></div></KevinCard>
      <KevinCard eyebrow="FORM" title="输入有边界，也有提示"><label for="demo-name">工作区名称</label><input id="demo-name" placeholder="例如：我的个人项目"/><p>表单与代码保持规整字体，手绘只用于品牌与角色。</p></KevinCard>
      <KevinCard eyebrow="EMPTY & ERROR" title="告诉你接下来能做什么"><div class="empty-demo"><KevinAvatar state="error" size={65} decorative/><div><strong>还没有连接到模型</strong><p>在设置中配置服务地址与凭据后，就可以开始工作。</p><a href="?">打开实际工作台 →</a></div></div></KevinCard>
      </div></section>
      <footer class="design-footer"><span>kevin · a little character, a clear workspace.</span><span>设计预览 / v0.1</span></footer>
    </main></div>;
}
