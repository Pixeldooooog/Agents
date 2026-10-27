import { For } from "solid-js";
import head from "../../../../assets/kevin-head-handdrawn-v1.png";

export function ChatWelcome(props: { choosePrompt: (prompt: string) => void }) {
  const suggestions = [
    {
      title: "理一理思路",
      hint: "把模糊的想法变成下一步",
      prompt: "我有一个想法，想和你一起梳理。请先问我想解决什么问题。",
    },
    {
      title: "一起看代码",
      hint: "从理解项目开始",
      prompt:
        "请先查看当前工作空间的项目结构，解释主要模块和入口，暂时不要修改文件。",
    },
    {
      title: "拆解一件事",
      hint: "把目标整理成行动清单",
      prompt: "帮我把接下来要做的一件事拆成行动清单。请先问我目标和约束。",
    },
  ];
  return (
    <div class="app-welcome">
      <div class="welcome-dog">
        <img src={head} alt="手绘天线小黑狗 Kevin" />
        <span>嘿，我在。</span>
      </div>
      <p class="welcome-overline">KEVIN’S NOTEBOOK · 一起做事的小天地</p>
      <h3>
        把想法放下来。
        <br />
        <em>我们一起，慢慢做好。</em>
      </h3>
      <p>一个问题、一个想法，或一件还没开始的事。</p>
      <div class="welcome-suggestions">
        <For each={suggestions}>
          {(item) => (
            <button onClick={() => props.choosePrompt(item.prompt)}>
              <strong>
                {item.title}
                <span>↗</span>
              </strong>
              <small>{item.hint}</small>
            </button>
          )}
        </For>
      </div>
    </div>
  );
}
