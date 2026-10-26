import { Show } from "solid-js";

export const kevinStates = ["ready", "listening", "thinking", "working", "done", "approval", "error"] as const;
export type KevinState = typeof kevinStates[number];
export const stateLabels: Record<KevinState, string> = {
  ready: "待命", listening: "倾听", thinking: "思考中", working: "执行中", done: "已完成", approval: "待确认", error: "需要处理"
};

/** Geometric UI interpretation of the approved antenna-dog sketch. */
export function KevinAvatar(props: { state?: KevinState; size?: number; decorative?: boolean; animated?: boolean }) {
  const state = () => props.state || "ready";
  return <svg viewBox="0 0 180 164" width={props.size || 64} height={props.size || 64}
    class={`kevin-dog is-${state()} ${props.animated === false ? "is-still" : ""}`}
    role={props.decorative ? undefined : "img"} aria-hidden={props.decorative ? "true" : undefined}
    aria-label={props.decorative ? undefined : `Kevin · ${stateLabels[state()]}`}>
    <g class="dog-head" stroke="var(--dog-ink, #272522)" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
      <g class="dog-antenna"><path d="M106 43 Q104 23 120 17" fill="none"/><circle class="antenna-light" cx="121" cy="15" r="6" fill="var(--signal, #dea74e)" stroke="none"/></g>
      <path d="M43 54 Q65 35 99 42 Q137 40 144 76 L153 121 Q152 149 92 151 Q32 152 29 123 L34 76Z" fill="var(--dog-paper, #fffaf0)"/>
      <path d="M45 55 Q57 57 48 86 L36 122 Q27 101 32 77Z M131 51 Q145 63 143 88 L149 121 Q133 110 128 85Z" fill="var(--dog-ink, #272522)" stroke="none"/>
      <g class="dog-ear ear-left"><path d="M44 53 Q29 42 17 64 Q3 84 13 102 Q25 110 36 83Z" fill="var(--dog-ink, #272522)"/><path d="M30 65 Q25 84 18 94" stroke="var(--dog-paper, #fffaf0)" stroke-width="2" fill="none"/></g>
      <g class="dog-ear ear-right"><path d="M130 50 Q146 41 161 59 Q177 76 163 87 Q150 90 143 66Z" fill="var(--dog-ink, #272522)"/><path d="M142 56 Q154 64 162 78" stroke="var(--dog-paper, #fffaf0)" stroke-width="2" fill="none"/></g>
      <g class="dog-eyes" fill="var(--dog-ink, #272522)">
        <Show when={state() === "done"} fallback={<><circle cx="63" cy="91" r="4" stroke="none"/><circle cx="116" cy="91" r="4" stroke="none"/></>}>
          <path d="M56 92 Q63 81 70 92 M109 92 Q116 81 123 92" fill="none"/>
        </Show>
      </g>
      <path d="M77 105 Q89 100 102 105 Q105 109 90 118 Q76 112 77 105Z" fill="var(--dog-ink, #272522)"/>
      <Show when={state() === "approval" || state() === "error"} fallback={<path d={state() === "thinking" ? "M89 119 Q95 123 89 127" : state() === "done" ? "M75 123 Q90 150 105 123Z" : "M90 118 Q88 137 74 126 M90 118 Q94 137 107 126"} fill="none"/>}>
        <ellipse cx="90" cy="129" rx="4" ry="5" fill="none"/>
      </Show>
      <circle cx="131" cy="117" r="4.5" fill="var(--signal, #dea74e)" stroke="none"/>
      <g class="work-rays" stroke="var(--signal-strong, #b57b26)" stroke-width="3"><path d="M134 12 L139 8 M136 22 L142 22"/></g>
    </g>
  </svg>;
}
