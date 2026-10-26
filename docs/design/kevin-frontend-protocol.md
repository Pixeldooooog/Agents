# Kevin 前端方案与协议

状态：方案稿（2026-10-26）。F0 已实现：`styles/tokens.css`、`copy/zh-CN.ts`、顶栏精简；F1–F5 尚未开始。本文回答四件事：界面怎么调整、风格怎么统一、App 用哪几种界面形态、前端与 Host 之间的协议怎么重写。

视觉变量、角色造型与组件原型以 [kevin-ui.md](kevin-ui.md) 为准，本文不重复定义颜色值；信息架构与 API 目标沿用 [产品规划 §10](../kevin-product-architecture-plan.md) 和 [实施规划 §4.3、§6、§9](../kevin-implementation-roadmap.md)，本文把三者落到可执行的前端契约上。

## 1. 现状评估

### 1.1 界面

| 现象 | 位置 | 问题 |
| --- | --- | --- |
| 品牌只覆盖了左上角和左栏 | `TopBar.tsx`、`ChatThread.tsx` | 头像和纸色已接入，但页面主体仍是旧控制台布局 |
| 右侧 60% 宽度是深色"Agent desktop"剧场 | `OperationStage*.tsx`、`operation-stage*.css` | 与暖纸色品牌冲突最大；空闲时没有任何信息量；手机上排在对话下面 |
| 中英混排 | 全局 | "Work with Kevin""What shall we work on?""Workspace ready"与"待命"、中文欢迎语并存 |
| 开发者词汇直接面向用户 | 输入框上方状态条、顶栏 | `openai-chat / model not set / no latency yet / default tool set`、`offline`、`Streaming` |
| 顶层导航是 Chat / Runs / Tasks / Settings | `App.tsx` | 按后端实体分页，不回答"Kevin 在做什么、要我决定什么、结果在哪" |
| 审批卡片展示工具名与原始参数 | `ToolApprovalPanel.tsx` | 用户看到 `patch.apply` 和 JSON，而不是"准备更新 README.md" |
| 设计原型与正式界面平行存在 | `?design`、`?design=workspace` | 原型只改本地演示状态，正式界面没有吸收第二版工作台思路 |

### 1.2 协议

| 现象 | 位置 | 问题 |
| --- | --- | --- |
| 线上事件只有 `{type, name, payload}` | `core/types/runtimeTypes.ts` `RuntimeEvent` | 没有 `event_id`、`sequence`、`schema_version`、`occurred_at`；无法去重、断线续传或检测丢事件 |
| `EventContract` 已定义但未使用 | `core/contracts/events.ts` | 契约和线上格式是两套东西 |
| 前端猜嵌套层级 | `web/runtime/eventHandlers.ts` | `frame.payload?.payload?.delta \|\| frame.payload?.delta` 这类双重读取，说明发送方格式不稳定 |
| 处理从未发出的事件 | 同上 | `code_start`、`web_search`、`browser_action` 运行时不会产生 |
| 未识别事件被原样 `JSON.stringify` 进活动列表 | 同上 | 原始数据直接进用户界面 |
| 工具展示逻辑写了两份 | `core/runtime/operationFrames.ts`、`web/runtime/operationProjector.ts` | 标题、场景、阶段在服务端和前端各推导一次，容易不一致 |
| 类型在每个客户端各写一份 | `web/types/*`、`terminal/protocol/terminalHostProtocol.ts` | `RuntimeEvent`、`ApprovalDecision`、`ModelProfile` 重复定义且已有差异 |
| 响应外壳与规划不一致 | `host/http/envelope.ts` | 现为 `{success, code, message, data}`；规划为 `{ok, request_id, data \| error}` |
| SSE 只绑定在一次 POST 请求上 | `POST /api/v1/agent/chat/stream` | 刷新页面或断线后无法重新订阅同一个 Run；没有 `Last-Event-ID` |
| 请求体可携带 `api_key`、`base_url` | `AgentChatPayload` | 凭据应只在 Host 配置中，不应由浏览器逐次发送 |

## 2. 界面调整

### 2.1 信息架构

把"按后端实体分页"改为"按用户问题组织"。第一阶段只做前三项，其余沿用现有页面并换皮。

| 目标页面 | 回答的问题 | 来源 | 阶段 |
| --- | --- | --- | --- |
| **首页（Today）** | Kevin 在做什么？要我决定什么？最近有什么结果？ | 新建；吸收 `app-conversation-v1` 的"等你开口" | F3 |
| **工作（Work）** | 这件事进行到哪、成果是什么 | 现有 Chat + 工作台原型合并 | F2 / F4 |
| **活动（Activity）** | 每一步具体做了什么，可审查、可导出 | 现有 Runs + RunInspector + OperationStage 的信息 | F5 |
| 任务（Tasks） | 后台任务列表 | 现有 TasksView，换皮 | 维持 |
| 设置（Settings） | 模型、权限、工作区 | 现有 SettingsView，换皮 | 维持 |

导航改为左侧窄栏（桌面）/ 底部标签（手机）：首页、工作、活动、设置。顶栏只保留：Kevin 头像 + 当前状态文字、当前工作区、暂停/继续。`Streaming` 开关、`Design` 入口移入设置的"开发者"分组；`offline` 改为仅在连接异常时出现的提示条。

### 2.2 深色剧场的去留

`OperationStage` 不再作为常驻右栏：

- 它承载的信息（当前工具、目标、进度）改由 **过程条** 表达：工作页里一条可折叠的时间线，默认显示自然语言摘要（"已读 3 个文件 · 草稿已整理"），展开后才看到参数与结果。
- 场景化动画保留为活动页里单个步骤的可选详情视图，换成纸色主题，不再使用整块深色背景。
- 相关 CSS（`operation-stage*.css`，约 670 行）在 F2 完成后删除。

### 2.3 文案

- 界面默认中文，所有用户可见字符串集中到 `apps/web/src/copy/zh-CN.ts`，为英文版预留同结构文件；不在组件里写死字符串。
- Kevin 的话用第一人称、短句、说明下一步："我先看一下现有说明。""草稿在这里，要不要按这个方向继续？"
- 工具名、协议名、模型 ID 只出现在活动页和设置页。工作页里一律说动作和对象："准备更新 README.md"，不说 `patch.apply`。
- 状态必须有文字，不能只靠表情或颜色（沿用 kevin-ui.md 的要求）。

## 3. 风格统一

### 3.1 设计变量

现有 `base.css` 的变量（`--bg #f4f5f2`、`--accent #0f6b5f` 青绿等）是改版前的配色，与品牌冲突。F0 阶段一次性替换为 kevin-ui.md 的变量，命名按用途：

| 变量 | 用途 | 取值来源 |
| --- | --- | --- |
| `--paper` / `--paper-raised` | 页面 / 卡片底色 | 页面纸色 / 卡片纸色 |
| `--ink` / `--ink-muted` | 正文 / 次要文字 | 正文 / 次要文字 |
| `--line` | 边线 | 边线 |
| `--signal` | 角色信号、主按钮底色、进行中强调 | 角色信号琥珀色 |
| `--state-ok` / `--state-wait` / `--state-error` / `--state-paused` | 任务状态语义色 | 新增，需同时通过浅色与深色对比度检查 |

规则：

- 删除青绿 `--accent` 和蓝色 `--blue`，全站只保留一个强调色（琥珀）。琥珀不用于小字，小字一律用 `--ink` 或 `--ink-muted`。
- 主按钮使用深墨底 + 纸色字（见工作台原型中的"这个方向可以"），琥珀圆形按钮只用于发送。
- 危险操作用文字和确认卡，不用大面积红色（沿用产品规划 §10.5）。
- 正式界面先只上浅色主题；深色主题在全部页面换完变量后一起上线，不做半套。

### 3.2 排版与形态

- 正文 Avenir Next / 苹方 / 微软雅黑；标题可用宋体；手写字体只用于品牌字标和少量批注（如原型里的"先理解你的材料"），不用于正文、表单、代码和审批内容。
- 卡片圆角 14–16px，按钮最小高度 40px，间距用 4/8/12/16/24/32/48 阶梯。
- 代码、Diff、路径使用等宽字体，保持高对比，不做纸张纹理。
- 动效只用于状态变化和新事件进入；不对每个 token 做动画；遵守 `prefers-reduced-motion`。

### 3.3 样式文件组织

现有 12 个 CSS 文件按历史功能拆分（`operation-stage-scenes.css` 等）。目标结构：

```text
styles/
  tokens.css        设计变量（唯一取值来源）
  base.css          重置、排版、焦点样式
  components/       每个通用组件一个文件：button、card、badge、avatar、composer
  surfaces/         每个界面形态一个文件：home、work、activity、settings
```

`kevin.css`、`work-canvas.css` 中已验证的样式迁入上述结构；旧文件在对应界面替换后删除。

## 4. App 界面形态

参考两版设计稿，App 有三种界面形态，按任务的**成果类型**选择，而不是所有任务都套工作台：

| 形态 | 对应设计稿 | 适用 | 主区域 |
| --- | --- | --- | --- |
| **开口** | `app-conversation-v1` 左图 | 没有进行中的工作 | 大头像 + "今天想做什么？" + 输入框 + 接着上次 |
| **陪你工作** | `app-conversation-v1` 右图 | 问答、短任务、单个文件改动 | 对话时间线，成果卡片和决策卡片嵌在时间线里 |
| **成果工作台** | `kevin-ui-preview`（第二版） | 有持续成果的较长任务：文档、调研、多文件改动 | 意图区 + 阶段路径 + 材料 / 成果 / 决策三栏 + 随时补充 |

切换规则：

1. 默认进入"陪你工作"。
2. 当 Run 产生第一个 `artifact.created`，或 Host 发出 `plan.updated`（有阶段路径）时，工作页顶部出现"切换到工作台"；用户也可以手动切换。不自动跳转，避免布局突变。
3. 工作台里的成果区只展示协议中的真实产物；材料区只展示真实读取过的来源（来自 `tool.completed` 的 `presentation.sources`）。没有真实数据时显示空状态，不放示例内容。
4. 简单问答不创建工作台。

### 4.1 共享组件

| 组件 | 职责 | 现状 |
| --- | --- | --- |
| `KevinAvatar` | 角色 SVG、状态、尺寸、动画开关 | 已有 |
| `AgentPresence` | 头像 + 状态文字 + 一句解释 | 已有，需改为读取协议投影 |
| `ProcessStrip` | 过程条：自然语言摘要，展开看步骤 | 新建，替代 OperationStage |
| `ArtifactCard` | 成果卡片：标题、类型、摘要、打开 / 查看差异 | 新建 |
| `DecisionCard` | 审批 / 需要回答：动作、目标、影响、选项 | 由 `ToolApprovalPanel` 改造 |
| `StagePath` | 阶段路径 | 工作台原型已有，需改为由 `plan.updated` 驱动 |
| `Composer` | 输入框 + 工作区 / 模型选择 + 暂停 | 现有输入框改造 |

### 4.2 角色状态由协议推导

头像状态是**纯函数**：输入是客户端投影（见 §5.6），输出是 kevin-ui.md 中的状态。优先级从高到低：

| 优先级 | 条件 | 状态 | 文字 |
| --- | --- | --- | --- |
| 1 | 连接中断或 Run 进入 `failed` | 需要处理 | "出了点问题" |
| 2 | 有未决的 `approval.requested` | 待确认 | "等你确认" |
| 3 | Run 处于 `waiting_input` | 待确认 | "等你回答" |
| 4 | 有 `tool.started` 尚未 `tool.completed` | 执行 | 当前步骤摘要 |
| 5 | Run 处于 `running` | 思考 | "在想" |
| 6 | 收到 `run.completed`（展示 3 秒后回落） | 完成 | "好了" |
| 7 | 其他 | 待命 | "待命" |

"完成"只由 `run.completed` 触发，不再用 `busy=false` 推断，这修正了 kevin-ui.md 中"完成仅预览"的限制。"倾听"在没有语音输入前不出现在正式界面。

## 5. 前端协议 v1

### 5.1 原则

- **事件是事实，界面是投影**：客户端不保存"真相"，所有界面状态都能由快照 + 事件重新计算出来。
- **展示信息由 Host 产生一次**：工具的标题、目标、场景、摘要在 Host 计算，客户端只渲染，不再各自推导。
- **契约放在 core**：类型定义在 `packages/core/src/contracts/`，Web 和终端都从 `@kevin/core` 导入，不再各写一份。
- **直接切换**：项目只在本地使用，v1 不保留旧事件名的兼容层，Host 与两个客户端同一次提交切换。

### 5.2 传输

| 用途 | 方式 |
| --- | --- |
| 命令（发消息、审批、取消、追加指令） | `POST` JSON，必须带 `Idempotency-Key` 头 |
| 查询（快照、列表） | `GET` JSON |
| 事件流 | `GET …/events`（SSE），支持 `Last-Event-ID` 断线续传 |
| 认证 | 回环地址同源访问免 token；非回环地址 `Authorization: Bearer` 必填（沿用现有 `ACCESS_TOKEN` 规则） |

命令和事件流分离：发送消息只返回 `run_id`，界面通过订阅该会话的事件流获得进展。刷新页面后重新订阅即可恢复，不依赖最初那次 POST 的连接。

### 5.3 响应外壳

与实施规划 §6.1 一致：

```ts
type ApiOk<T> = { ok: true; request_id: string; data: T };
type ApiError = {
  ok: false;
  request_id: string;
  error: { code: string; message: string; retryable: boolean; details?: Record<string, unknown> };
};
```

`error.code` 使用稳定的蛇形命名（`approval_not_found`、`run_not_active`、`invalid_payload`），界面按 code 选择文案，`message` 只作为兜底。

### 5.4 接口

v1 只定义当前界面需要的接口；任务、记忆、连接器沿用实施规划 §6 的路径，届时补充。

```text
GET    /api/v1/agent                          Kevin 身份、当前状态、工作区、模型摘要
GET    /api/v1/conversations?cursor=          会话列表（"接着上次"）
POST   /api/v1/conversations                  新建会话
GET    /api/v1/conversations/:id              会话快照（见 5.6）
POST   /api/v1/conversations/:id/messages     发送消息 → { run_id }
GET    /api/v1/conversations/:id/events       SSE 事件流
POST   /api/v1/runs/:id/cancel                取消
POST   /api/v1/approvals/:id/decision         { decision: "allow_once" | "allow_for_run" | "deny", note? }
GET    /api/v1/runs/:id/activity              活动页：完整事件 + 原始参数与结果
GET    /api/v1/artifacts/:id                  产物内容 / 下载
```

发送消息的请求体只包含用户意图，不包含凭据：

```ts
type SendMessage = {
  text: string;
  mode: "chat" | "task";          // 用户明确选择，不由系统猜测（实施规划 §9.2）
  attachments?: { path: string }[];
  model_profile?: string;          // 只引用 Host 中已配置的 profile 名
};
```

### 5.5 事件

外壳统一为 `KevinEvent`，与实施规划 §4.3 及 `core/contracts/events.ts` 合并为一个定义：

```ts
type KevinEvent<T extends KevinEventType = KevinEventType> = {
  event_id: string;               // 全局唯一；SSE 的 id 字段使用它
  schema_version: 1;
  type: T;
  occurred_at: string;            // ISO 8601
  actor: "user" | "kevin" | "tool" | "system";
  conversation_id?: string;
  run_id?: string;
  sequence?: number;              // 同一 Run 内从 1 递增；有 run_id 时必填
  payload: KevinEventPayloads[T];
};
```

SSE 帧格式固定为：`id: <event_id>`、`event: <type>`、`data: <整个 KevinEvent 的 JSON>`。`data` 里就是完整事件，不再嵌套第二层 `payload`。

**界面所需的事件目录：**

| 类型 | payload 要点 | 界面用途 |
| --- | --- | --- |
| `run.started` | `mode`、`goal` | 头像进入思考；工作页出现进行中的 Run |
| `run.waiting_input` | `question`、`choices?` | 决策卡片（回答型） |
| `run.completed` | `summary` | 头像"完成"；过程条收起 |
| `run.failed` | `error`（同 5.3 的 error 结构）、`actions`（`retry`/`edit`/`view_activity`/`cancel`） | 失败卡片的四个动作（实施规划 §9.2） |
| `run.cancelled` | `reason?` | 过程条标记已取消 |
| `message.delta` | `message_id`、`text` | 流式文字，按 `message_id` 追加 |
| `message.completed` | `message_id`、`text` | 用最终文本覆盖，纠正流式中的偏差 |
| `tool.started` | `tool_call_id`、`presentation` | 过程条新增一步；头像进入执行 |
| `tool.completed` | `tool_call_id`、`status: "ok" \| "error"`、`presentation` | 更新该步骤；`presentation.sources` 进入材料区 |
| `approval.requested` | `approval_id`、`presentation`、`impact`、`options` | 决策卡片（审批型） |
| `approval.decided` | `approval_id`、`decision`、`decided_by` | 关闭决策卡片 |
| `artifact.created` / `artifact.updated` | `artifact_id`、`kind`、`title`、`summary`、`version` | 成果卡片 / 工作台成果区 |
| `plan.updated` | `stages: { id, title, state: "todo" \| "active" \| "done" }[]` | 工作台阶段路径 |

`presentation` 是 Host 给出的人类可读描述，客户端直接渲染：

```ts
type ToolPresentation = {
  title: string;                   // "读取 README.md"、"准备更新 README.md"
  target?: string;                 // 路径、域名、命令摘要
  scene: "file" | "edit" | "search" | "web" | "terminal" | "git" | "other";
  summary?: string;                // 完成后的一句话结果："找到 3 处相关说明"
  sources?: { title: string; uri: string; excerpt?: string }[];
  diff?: { path: string; additions: number; deletions: number };
};

type ApprovalImpact = {
  risk: "low" | "medium" | "high";
  paths?: string[];
  commands?: string[];
  domains?: string[];
  diff_preview?: string;           // 统一 diff 文本，界面折叠显示
};
```

原始参数与原始结果**不进入**事件流，只通过 `GET /runs/:id/activity` 获取，用于活动页的"展开技术细节"。这样工作页拿不到也就渲染不出原始 JSON。

**现有事件名迁移：**

| 现在 | v1 |
| --- | --- |
| `run_created` | `run.started` |
| `text_delta` | `message.delta` |
| `model_message` | `message.completed` |
| `tool_start` | `tool.started` |
| `tool_result` | `tool.completed` |
| `tool_approval_required` | `approval.requested` |
| `tool_approval_decision` | `approval.decided` |
| `done` | `run.completed` |
| `error` | `run.failed` |
| `turn_started` / `turn_finished`（终端） | 删除；由 `run.*` 表达 |
| `code_start` / `web_search` / `browser_action`（仅前端处理） | 删除；统一为 `tool.*` + `presentation.scene` |

### 5.6 客户端投影

```ts
type ConversationProjection = {
  conversation_id: string;
  last_event_id?: string;
  run?: {
    run_id: string;
    state: "running" | "waiting_input" | "waiting_approval" | "completed" | "failed" | "cancelled";
    last_sequence: number;
  };
  messages: { message_id: string; role: "user" | "kevin"; text: string; streaming: boolean }[];
  steps: { tool_call_id: string; status: "running" | "ok" | "error"; presentation: ToolPresentation }[];
  decisions: Decision[];           // 未决的审批与提问
  artifacts: { artifact_id: string; kind: string; title: string; summary?: string; version: number }[];
  stages?: { id: string; title: string; state: "todo" | "active" | "done" }[];
};
```

规则：

1. **启动**：`GET /conversations/:id` 返回 `ConversationProjection` 形状的快照，包含 `last_event_id`；然后带 `Last-Event-ID` 订阅事件流。
2. **应用事件**：纯函数 `reduce(projection, event) → projection`，放在 `@kevin/core/contracts` 中，Web 与终端共用，并有单元测试。
3. **去重**：`event_id` 已处理则忽略（重连可能重复投递）。
4. **缺口**：同一 Run 的 `sequence` 不连续时，丢弃本地投影，重新拉快照。
5. **未知事件类型**：忽略并在开发模式打印警告；不进入用户界面。
6. **头像状态**：`deriveAvatarState(projection, connection)`，按 §4.2 的优先级实现，同样有单元测试。

### 5.7 终端客户端

终端走同一套契约：Host 在 stdio JSONL 上发送同样的 `KevinEvent`，终端用同一个 `reduce` 构建投影。终端特有的控制消息（`sessions`、`model_profiles`、`doctor` 等列表类结果）保留为独立的 `control.*` 响应，不混入 Run 事件流。

## 6. 实施分期

每一期都能独立合入，并且合入后 `bun run check` 通过。

| 期 | 内容 | 验收 |
| --- | --- | --- |
| **F0 风格基础** | `tokens.css` 替换旧变量；删除青绿与蓝色；文案集中到 `copy/zh-CN.ts`；顶栏去掉开发者开关 | 1440 / 1280 / 390 / 320px 截图；无青绿残留；键盘焦点可见 |
| **F1 协议 v1** | core 中定义 `KevinEvent`、payload、`reduce`、`deriveAvatarState`；Host 发出新事件与 `presentation`；新增快照与 SSE 订阅接口；响应外壳切换；两个客户端同时切换；删除旧事件名 | `reduce` 与 `deriveAvatarState` 单元测试；断线重连不重复、不丢事件的集成测试；终端冒烟测试通过 |
| **F2 陪你工作** | 工作页改为对话时间线 + `ProcessStrip` + `DecisionCard` + `ArtifactCard`；删除 `OperationStage` 与相关 CSS | 一次真实 Run（fixture 模型）完整走过：读文件 → 审批 → 改动 → 完成；审批卡片不出现工具 ID 与原始 JSON |
| **F3 首页** | 开口形态 + 接着上次 + 需要你处理 + 最近成果 | 有未决审批时首页可见并可直接处理 |
| **F4 成果工作台** | 工作台接入真实 `artifact.*`、`plan.updated`、`presentation.sources`；移除示例数据 | 工作台内容与活动页一一对应，无示例数据 |
| **F5 活动页** | Runs + RunInspector 合并为活动页，展开查看原始参数与结果，导出 JSONL | 任意步骤可从工作页跳转到活动页对应位置 |

F0 与 F1 互不依赖，可以并行；F2 依赖两者；F3–F5 依赖 F2。

## 7. 待定问题

1. **会话与 Run 的关系**：当前 Host 以 Run 为中心，没有 Conversation 实体。F1 需要先决定：Conversation 是否在 B2（SQLite）之前以 JSON store 实现，还是 F1 先用"一个 Run 即一个会话"过渡。
2. **`plan.updated` 的来源**：阶段路径由模型通过工具显式声明，还是由 Host 根据规划工具（`planning/`）推导。前者更准确，后者不依赖模型配合。
3. **产物的存储**：`artifact.*` 需要 Host 有产物存储；目前只有 trace 中的 `artifacts` 字段。可先以工作区内文件 + 元数据记录实现。
4. **深色主题上线时间**：建议在 F2 之后、所有页面换完变量后统一上线。
5. **英文界面**：文案已集中，是否在 F0 同时提供英文版，还是等 README 以外有英文用户再做。
