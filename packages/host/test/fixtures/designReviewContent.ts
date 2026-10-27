/** Rich output for browser typography and untrusted-Markdown acceptance. */
export const designReviewContent = `## 把想法，变成一个清楚的开始

我建议把 Kevin 做成一本**会陪你一起工作的手册**。打开时很轻，真正做事时，每一步又能看得清楚。

### 先把这三件事做好

1. **对话有呼吸感**：正文像笔记一样自然展开，长回复也能轻松阅读。
2. **过程可以追溯**：工具操作进入右侧工作手记，需要你确认的事留在对话里。
3. **结果方便带走**：文字、代码和表格都保持清晰，不藏在一层层气泡里。

> 狗狗是陪伴感的来源；清楚的反馈，是信任感的来源。

| 场景 | 界面应该怎么回应 |
| --- | --- |
| 我在思考 | 安静的状态提示，不打断阅读 |
| 需要确认 | 说明操作，展开参数，再让你决定 |
| 正在执行 | 把实际步骤记下来 |

### 一个简单的边界

\`\`\`typescript
const workspace = {
  conversation: "表达目标、讨论和确认",
  notebook: "观察工具步骤和结果",
  companion: "用小幅动作表达当前状态",
};
\`\`\`

这只是用于界面验收的示例回复。你可以继续补充想法，我们再把细节一起磨好。
`;

export const unsafeMarkdownContent = `# 安全渲染检查
<script>window.__kevinUnsafe = true</script>
<img src=x onerror="window.__kevinUnsafe = true">

[危险链接](javascript:alert(1))

**这段正常内容应该保留**
`;
