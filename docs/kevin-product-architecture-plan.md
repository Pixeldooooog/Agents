# Kevin：个人长期运行 Agent 产品规划

> 状态：方案基线
> 目标：把当前 `Agents` 仓库收敛为一个可长期运行、可审查、可配置、可分发的单 Agent 产品，产品名为 **Kevin**。
> 范围：本方案覆盖产品定位、能力边界、系统架构、配置、数据库、界面、仓库治理、分发方式、迁移路线和验收标准。

> 复核说明：本文件描述产品方向；可执行任务、数据库约束、API 契约、恢复语义和发布门禁以 [Kevin 实施规划与交付计划](kevin-implementation-roadmap.md) 为准。当前仓库尚未完成这些目标能力，文中“应具备”不等于“已经支持”。

## 1. 结论先行

Kevin 不应该继续做一个“拥有很多工具的通用 Agent SDK”。它应该成为一个有名字、有记忆、有工作空间、有后台任务、有权限边界和有活动记录的个人 Agent。

用户面对的核心对象只有一个：**Kevin**。用户可以和 Kevin 对话，给 Kevin 一个长期目标，连接必要的应用和本地电脑，查看它正在做什么，在关键动作前批准它，并随时暂停、修改或恢复工作。

当前仓库已经拥有可复用的基础：TypeScript runtime、多模型 profile、工具注册、权限与审批、Run/Task/Session 状态、MCP、Terminal、Web UI 和 SDK 协议。需要做的是产品收敛和基础设施升级，而不是继续横向增加更多抽象。当前 Task 仍由单进程 service 驱动，状态仍以 JSON store 为主，不能把它们描述成已经具备 Durable Execution 或云端常驻能力。

建议的产品形态：

- 默认是一个 Kevin 实例，一个用户一个 Agent 身份。
- 对话、任务、记忆、连接器、工作空间和活动全部围绕 Kevin 组织。
- 支持前台即时任务和后台持续任务，但后台任务必须可见、可暂停、可恢复。
- 高风险动作默认需要批准；低风险动作可以自动执行。
- 本地优先运行，数据库和远程执行能力采用可替换适配器，避免一开始被云基础设施绑死。
- 第一阶段聚焦个人效率和开发工作，不承诺企业多租户、多 Agent 编排和全自动无人值守。

## 2. 对 Dot 的研究与可借鉴之处

公开资料把 Dot 描述为一个 always-on agent：它拥有自己的工作空间和浏览器，可以持续推进项目；用户可以在桌面、Web、移动端查看任务进度、结果和输入请求，也可以连接电脑和外部应用。官方资料还强调了连接应用的权限边界、活动查看和需要用户批准的动作。

参考资料：

- [OpenAI：Introducing dots](https://openai.com/index/introducing-dots/)
- [ChatGPT Learn：Meet dots](https://learn.chatgpt.com/docs/dots)
- [ChatGPT Learn：Connect computers and apps](https://learn.chatgpt.com/docs/dots/computers-and-apps)
- [OpenAI Help：Getting started with your dot](https://help.openai.com/en/articles/20001530-getting-started-with-your-dot)

Kevin 应借鉴这些产品原则，而不是复制其云基础设施：

| Dot 的产品原则 | Kevin 的落地方式 |
|---|---|
| Agent 有持续身份 | `agent_profile` 保存名称、头像、人格、目标和行为规则 |
| Agent 有自己的工作空间 | 每个 Kevin 实例有独立 workspace、文件索引和运行目录 |
| 工作可以在后台继续 | `task`、`run`、调度器和恢复状态组成长期任务系统 |
| 用户可以随时介入 | 活动流、审批卡片、暂停、继续、追加指令 |
| 连接应用但权限受控 | Connector + capability + scope + approval policy |
| 多端查看同一个工作 | Web 是主界面，Terminal 是开发和故障排查入口 |
| 工作结果可审查 | Event、Artifact、Decision、Approval、Cost 形成可查询活动记录 |

Kevin 不应直接承诺“永远在线”或“完全自主”。第一阶段应把它定义为：**可持续运行、可观察、可暂停、可恢复的个人 Agent**。

## 3. 产品定位与非目标

### 3.1 目标用户

第一目标用户是需要持续推进代码、资料、文档和个人工作的人。典型任务包括：

- 在一个代码仓库中持续修复问题、运行测试并提交变更。
- 收集资料，整理成报告、计划或文档。
- 定时检查项目状态，发现变化后生成摘要或提醒。
- 在本地文件、Git、Web 和已连接服务之间完成有限范围的工作流。
- 维护一个长期项目上下文，而不是每次从零开始对话。

### 3.2 非目标

第一阶段明确不做：

- 多 Agent 群聊、复杂团队编排和 Agent 市场。
- 企业级多租户计费、组织层级和复杂 RBAC。
- 默认可发送邮件、发布内容、付款或修改生产系统。
- 把所有工具都包装成“自动执行”；高风险动作必须走策略和审批。
- 追求与 OpenAI、Claude 或 Codex 的全部功能对等。

## 4. 产品对象模型

用户在界面上应该理解以下对象：

```mermaid
flowchart LR
  User[用户] --> Kevin[Kevin Agent]
  Kevin --> Workspace[工作空间]
  Kevin --> Conversation[对话]
  Kevin --> Task[后台任务]
  Kevin --> Memory[记忆]
  Kevin --> Connector[连接器]
  Kevin --> Activity[活动记录]
  Task --> Run[执行运行]
  Run --> Event[事件]
  Run --> Artifact[产物]
  Run --> Approval[审批]
```

- **Agent**：唯一的 Kevin 身份、行为和全局配置。
- **Workspace**：Kevin 可以读取和修改的文件、仓库、运行目录和索引。
- **Conversation**：用户与 Kevin 的交流上下文。
- **Task**：一个可持续推进的目标，可以被启动、暂停、恢复和取消。
- **Run**：Task 的一次具体执行尝试。
- **Event**：模型、工具、审批、状态和错误事件。
- **Artifact**：报告、补丁、文件、截图、链接等结果。
- **Memory**：用户明确保存或系统确认过的长期信息。
- **Connector**：外部应用或本地设备连接，包含权限范围。
- **Approval**：需要用户确认的具体动作，而不是模糊的“允许 Agent”。

## 5. 建议的整体架构

```mermaid
flowchart TB
  subgraph Clients
    Web[Kevin Web App]
    Terminal[Kevin Terminal]
    LocalBridge[Kevin Local Bridge]
  end

  subgraph Host
    API[HTTP API / SSE / WebSocket]
    Auth[Local Auth & Session]
    Scheduler[Task Scheduler]
    Worker[Run Worker]
  end

  subgraph Core
    Orchestrator[Agent Orchestrator]
    Context[Context & Memory Manager]
    Policy[Permission Policy Engine]
    Registry[Tool / Connector Registry]
    Events[Event Bus]
    Artifacts[Artifact Manager]
  end

  subgraph Storage
    DB[(SQLite / Postgres Adapter)]
    Files[Workspace & Artifact Files]
    Index[(FTS / Vector Index)]
  end

  subgraph Providers
    Models[Model Provider Adapters]
    MCP[MCP Connectors]
    Computer[Browser / Computer Tools]
  end

  Web --> API
  Terminal --> API
  LocalBridge --> API
  API --> Auth
  API --> Scheduler
  API --> Worker
  Worker --> Orchestrator
  Orchestrator --> Context
  Orchestrator --> Policy
  Orchestrator --> Registry
  Orchestrator --> Events
  Orchestrator --> Artifacts
  Orchestrator --> Models
  Registry --> MCP
  Registry --> Computer
  Events --> DB
  Context --> DB
  Scheduler --> DB
  Artifacts --> Files
  Context --> Index
  DB --> Files
```

### 5.1 代码分层

```text
apps/
  web/                    Kevin 主界面
  terminal/               开发者和故障排查界面
  desktop/                可选：Tauri/Electron 外壳，第二阶段再做

packages/
  core/                   Agent domain、run loop、tool contracts
  host/                   HTTP、SSE、WebSocket、scheduler、auth
  db/                     Store interface、SQLite adapter、migrations
  providers/              OpenAI/Anthropic/Gemini/compatible adapters
  connectors/             MCP、GitHub、Slack、Notion 等连接器
  policy/                 permissions、approval、sandbox policy
  workspace/              workspace、file index、artifact storage
  observability/          event schema、trace、metrics、diagnostics
  config/                 typed config、validation、redaction

packages/core/src/ 应保持与 UI、数据库和具体 provider 解耦。入口文件只做 wiring；业务行为放入可测试的 focused modules。
```

### 5.2 单 Agent 收敛原则

现有 `team.*`、`agent.run` 等多 Agent 相关能力不应继续作为 Kevin 的主产品入口。建议分三步处理：

1. 第一阶段从默认工具列表和主界面隐藏，保留兼容代码并标记 deprecated。
2. 第二阶段把多 Agent 能力移到 `packages/experimental` 或独立扩展包。
3. 当 Kevin 的单 Agent 任务、记忆、审批和恢复稳定后，再决定是否重新引入协作能力。

## 6. Runtime 设计

### 6.1 Run 生命周期

```text
queued
  -> preparing
  -> running
  -> waiting_for_input
  -> waiting_for_approval
  -> paused
  -> completed | failed | cancelled | expired
```

每次状态转换都写入不可变 Event，并带有 `run_id`、`task_id`、`request_id`、时间、来源和版本。恢复时从最后一个可恢复 checkpoint 继续，而不是只依赖内存中的对话对象。

### 6.2 工作模式

- **Chat mode**：短交互、低延迟，适合问答和即时修改。
- **Task mode**：有目标、有步骤、有产物，适合持续工作。
- **Scheduled mode**：按时间或事件触发，必须显示下次执行时间和权限范围。
- **Review mode**：只读分析和规划，不执行写入动作。

### 6.3 Agent 循环

1. 读取用户消息、Task 目标和 workspace 状态。
2. 生成执行计划或直接进入单步处理。
3. 根据 Policy Engine 判断工具是否可用、是否需要批准。
4. 执行工具并写入 ToolStart/ToolResult 事件。
5. 保存中间 checkpoint 和产物引用。
6. 判断继续、等待输入、等待审批或结束。
7. 向 Web、Terminal 和 SDK 投影同一套事件。

### 6.4 长任务必须具备的能力

- 幂等 `request_id` 和工具调用 ID。
- 进程重启后恢复 queued/running/paused 状态。
- 单次运行的最大时间、最大 token、最大成本和最大工具次数。
- 失败重试策略，区分可重试错误和业务错误。
- 任务取消传播到当前工具和子进程。
- 每个工具调用的输入摘要、输出摘要、耗时和错误。
- 用户追加指令后保留原始任务目标和决策记录。

## 7. 配置设计

配置分为四层，优先级从高到低：命令行参数 > 环境变量 > 用户配置 > 默认配置。

### 7.1 推荐配置文件

用户配置目录：

```text
~/.kevin/
  config.toml
  credentials.json        # 仅保存引用或加密凭据，不进入 Git
  kevin.db
  workspaces/
  artifacts/
  logs/
```

项目配置：

```text
.kevin/
  project.toml
  instructions.md
  policy.toml
  connectors.toml
```

### 7.2 `config.toml` 示例

```toml
[kevin]
name = "Kevin"
locale = "zh-CN"
timezone = "America/New_York"
profile = "developer"

[server]
host = "127.0.0.1"
port = 8020
public_url = "http://localhost:8020"

[storage]
driver = "sqlite"
database_url = "~/.kevin/kevin.db"
artifact_root = "~/.kevin/artifacts"
workspace_root = "~/.kevin/workspaces"

[models.default]
provider = "openai"
model = "gpt-5"
base_url = "https://api.openai.com/v1"

[models.fast]
provider = "openai"
model = "gpt-5-mini"

[agent]
system_prompt_file = "~/.kevin/instructions.md"
max_context_tokens = 128000
max_tool_iterations = 40
max_run_minutes = 30
max_cost_usd = 2.0

[policy]
default_mode = "ask-on-write"
allow_network = false
allow_shell = false
allow_background_tasks = true

[workspace]
read_paths = ["~/Projects"]
write_paths = ["~/Projects/active"]
exclude = ["**/.env", "**/node_modules", "**/.git/objects"]

[notifications]
enabled = true
channels = ["web", "terminal"]

[connectors]
enabled = ["filesystem", "git", "web"]
```

### 7.3 配置原则

- Secret 不写入 TOML，不打印到日志，不随诊断包导出。
- 每个配置项必须有类型、默认值、来源和脱敏显示方式。
- Provider 配置与 Agent 行为配置分离。
- 工具权限不能只由 `enabled_tools` 字符串表达，必须升级为结构化 Policy。
- 运行时配置变更要有审计事件，并明确是否影响当前 Run。

## 8. 数据库设计

### 8.1 为什么从 JSON 迁移到 SQLite

当前 JSON state store 适合单进程开发，但 Kevin 的核心体验要求任务恢复、活动查询、审批列表、分页、并发写入和全文搜索。SQLite 是本地优先产品的合理第一步；通过 `Store` 接口保留 Postgres 适配器，未来再支持远程部署。

### 8.2 核心表

```text
agents
  id, name, slug, avatar, system_prompt, timezone, created_at, updated_at

workspaces
  id, agent_id, name, root_path, status, policy_json, created_at, updated_at

conversations
  id, agent_id, workspace_id, title, status, created_at, updated_at

messages
  id, conversation_id, role, content_json, sequence, created_at

tasks
  id, agent_id, workspace_id, conversation_id, title, goal, status,
  schedule_json, priority, next_run_at, created_at, updated_at

runs
  id, task_id, conversation_id, status, attempt, request_id,
  model_profile, started_at, finished_at, error_code, checkpoint_json

events
  id, run_id, task_id, sequence, type, actor, payload_json, created_at

approvals
  id, run_id, tool_call_id, action_summary, risk, status,
  requested_at, decided_at, decided_by, decision_reason

tool_calls
  id, run_id, event_id, name, arguments_json, result_json,
  status, risk, started_at, finished_at

memories
  id, agent_id, workspace_id, kind, content, source, confidence,
  embedding_ref, created_at, updated_at, expires_at

connectors
  id, agent_id, type, name, status, config_json, secret_ref, created_at, updated_at

connector_permissions
  id, connector_id, capability, resource_scope, mode, expires_at

artifacts
  id, run_id, workspace_id, type, name, path, mime_type, sha256, metadata_json, created_at

schedules
  id, task_id, expression, timezone, enabled, next_run_at, last_run_at

usage_records
  id, run_id, provider, model, input_tokens, output_tokens, cost_usd, created_at

settings_audit
  id, actor, key, old_value_redacted, new_value_redacted, created_at
```

### 8.3 索引与保留策略

- `events(run_id, sequence)`：按运行重放。
- `tasks(agent_id, status, next_run_at)`：调度器取任务。
- `approvals(status, requested_at)`：审批中心查询。
- `messages(conversation_id, sequence)`：消息分页。
- `memories(agent_id, workspace_id, kind)`：上下文注入。
- `artifacts(run_id, created_at)`：结果列表。
- 对消息和事件做可配置保留；原始事件可归档到 JSONL 或对象存储。
- 大文件不进入数据库，只保存路径、哈希、MIME 和元数据。

### 8.4 迁移策略

1. 定义 `Store` 接口，先写 SQLite adapter。
2. 为 JSON store 增加只读导入器。
3. 首次启动执行 JSON → SQLite 导入并生成备份。
4. 通过 migration table 管理 schema 版本。
5. 默认停止新功能继续依赖 JSON store。
6. 增加 `kevin doctor storage` 检查数据库、迁移和文件权限。

## 9. 工具与连接器策略

工具不再按“能不能做”分类，而按风险和产品价值分类：

### Tier 0：默认开启

- 读取文件、列目录、搜索文本。
- 读取 Git 状态、diff、日志。
- 读取当前 Session、Task 和 Activity。
- 生成摘要、计划和报告。

### Tier 1：首次确认后可记住

- 写文件、应用 Patch、创建分支。
- 运行测试、启动受限开发命令。
- 读取指定的 Web 页面或 MCP 资源。
- 创建后台任务和 Schedule。

### Tier 2：每次动作确认

- 删除文件、执行高风险 Shell。
- 推送 Git、发布内容、发送消息。
- 修改外部系统数据。
- 使用本地电脑控制浏览器或桌面。

### Tier 3：默认禁止

- 读取密钥、SSH 私钥、浏览器 Cookie。
- 付款、转账、绕过安全控制。
- 对生产系统执行不可逆操作。

连接器接口建议：

```ts
interface KevinConnector {
  id: string;
  capabilities(): ConnectorCapability[];
  health(): Promise<ConnectorHealth>;
  execute(input: ConnectorAction, context: ConnectorContext): Promise<ConnectorResult>;
  revoke(): Promise<void>;
}
```

每个连接器都必须声明 capability、resource scope、读写模式和 approval 默认值。MCP 适合作为连接器协议，但不能直接把远程工具全部视为可信工具。

## 10. Web 界面设计

### 10.1 信息架构

```text
左侧导航
  Kevin
  对话
  任务
  活动
  记忆
  连接
  工作空间
  设置

主区域
  当前页面内容

右侧上下文栏
  当前任务状态
  待审批动作
  最近产物
  Token / 时间 / 成本
```

### 10.2 首页：Today

首页不应该是空白聊天框，而应该回答三件事：

1. Kevin 正在做什么？
2. 需要我决定什么？
3. 今天有哪些结果？

建议组件：

- 顶部身份卡：Kevin 头像、状态、当前工作空间、暂停/继续按钮。
- “正在进行”卡片：任务标题、当前步骤、最近事件、预计下一步。
- “需要你处理”卡片：审批、补充信息、失败重试。
- “最近产物”列表：报告、补丁、文件、链接。
- “快捷交办”输入框：创建聊天或后台任务。
- 可选的每日摘要，不主动打扰用户，除非有配置好的通知规则。

### 10.3 对话页

- 消息流和工具活动在同一条时间线上，但工具细节默认折叠。
- 每个工具调用显示动作、目标、状态和风险，而不是直接展示原始 JSON。
- 代码变更用 Diff Preview，文件结果用 Artifact Card。
- Agent 正在等待时，明确显示“等待审批”“等待你的回答”或“后台执行中”。
- 输入框支持切换 Chat / Task / Review。

### 10.4 活动页

活动页是 Kevin 产品的信任中心：

- 按时间、任务、工具、状态筛选。
- 展开后看到模型回复、工具调用、审批决策和产物。
- 支持复制事件 ID、导出 JSONL、重试失败 Run。
- 用户看到的是人类可读摘要，开发者可以展开技术细节。

### 10.5 视觉方向

- 使用暖白背景、深墨色文字、单一强调色，避免“霓虹 AI 仪表盘”。
- Kevin 的视觉锚点是一个小型几何头像或圆点标记，但不模仿 OpenAI 品牌图形。
- 任务状态使用少量明确颜色：运行、等待、成功、失败、暂停。
- 主要操作保持一个主色按钮，危险操作使用文字和确认卡，而不是大片红色。
- 动效只用于状态变化和新事件进入，不对每个 token 做过度动画。
- 空状态给出可执行示例：修复仓库测试、整理资料、建立每周检查任务。

## 11. Terminal 界面

Terminal 不是第二套产品逻辑，而是 Web API 的另一个客户端：

- `/ask`：即时对话。
- `/task`：创建后台任务。
- `/tasks`：查看和恢复任务。
- `/activity`：查看事件。
- `/approve`：处理审批。
- `/connect`：配置本地连接器。
- `/model`：选择模型。
- `/doctor`：诊断配置、数据库、Provider 和 workspace。

Terminal 适合开发和故障恢复；普通用户的主体验应放在 Web。

## 12. 仓库重命名与分发设计

### 12.1 名称建议

产品名：`Kevin`

推荐仓库名：`kevin-agent`

推荐 npm workspace 名称：

```text
@kevin/core
@kevin/host
@kevin/db
@kevin/providers
@kevin/connectors
@kevin/web
```

命令名：

```text
kevin
kevin host
kevin task run <id>
kevin doctor
```

建议保留一次迁移说明：`Agents` → `Kevin`。Git 历史不需要重写，仓库 URL 如果要改，应保留旧地址跳转。

### 12.2 推荐仓库结构

```text
kevin-agent/
  apps/
    web/
    terminal/
  packages/
    core/
    host/
    db/
    providers/
    connectors/
    policy/
    workspace/
    observability/
    config/
  migrations/
  config/
    defaults.toml
    examples/
  deploy/
    Dockerfile
    docker-compose.yml
    healthcheck.sh
  docs/
    product.md
    architecture.md
    configuration.md
    security.md
    connectors.md
    self-hosting.md
    contributing.md
    adr/
  examples/
    minimal-config/
    developer-agent/
  scripts/
  .github/
    workflows/ci.yml
    ISSUE_TEMPLATE/
    pull_request_template.md
  LICENSE
  README.md
  README.zh-CN.md
  CHANGELOG.md
  SECURITY.md
  CONTRIBUTING.md
```

### 12.3 对外可分发的仓库要求

- README 首屏说明 Kevin 是什么、适合谁、30 秒启动方式和安全边界。
- 提供 `bunx kevin init` 或安装脚本，减少手工复制配置。
- 提供 `.env.example`、配置校验和 `kevin doctor`。
- 提供 SQLite 默认模式和 Docker Compose 可选模式。
- 所有命令返回稳定退出码，日志不泄露密钥。
- 发布包包含版本、变更记录、迁移说明和兼容性矩阵。
- 文档区分本地开发、个人自托管和生产部署。
- 增加截图、短 GIF 或演示视频，展示“创建任务—后台执行—审批—产物”的完整链路。
- 增加 `SECURITY.md` 和漏洞报告方式。
- CI 至少覆盖类型检查、单元测试、Web 构建、数据库迁移、Docker clean-host 构建和基本 E2E。

## 13. 迁移实施路线

### Phase 0：产品收敛与命名

- 统一 Kevin 品牌、命令、包名和配置前缀。
- 更新 README、功能矩阵和架构图。
- 把多 Agent/team 能力从默认产品面隐藏。
- 建立 ADR，记录单 Agent 决策。

验收：新用户只看 README 就能理解 Kevin 是什么，并能启动一个本地 Agent。

### Phase 1：数据库与状态基础

- 新增 `packages/db`。
- 定义 Store interface 和 SQLite migration runner。
- 实现 JSON 导入、备份和回滚。
- 把 Run、Task、Event、Approval、Artifact、Memory 迁移到 SQLite。

验收：重启进程后任务状态、审批和活动可以恢复，现有 JSON 数据可以导入。

### Phase 2：长期任务与调度

- 实现任务队列、worker、checkpoint、取消、重试和过期。
- 增加 schedule worker 和单实例锁。
- 增加运行上限、成本上限和工具次数上限。

验收：模拟进程中断后任务可恢复；重复请求不会重复执行不可幂等动作。

### Phase 3：权限、连接器和本地桥

- 把现有权限逻辑升级为 Policy Engine。
- 实现文件、Git、Web、MCP 的 connector contract。
- 增加本地电脑连接的显式授权和撤销。
- 建立 Tier 0~3 风险分级。

验收：高风险操作必定进入审批；撤销连接后工具立即不可用；审计记录完整。

### Phase 4：Kevin Web 产品化

- 重做 Today、Chat、Tasks、Activity、Memory、Connections、Settings。
- 同一事件流同时驱动 Web 和 Terminal。
- 增加产物预览、Diff、审批中心和错误恢复。

验收：一个用户可以仅通过 Web 完成创建任务、审批、查看结果和恢复失败任务。

### Phase 5：分发与生产门禁

- 完成 CLI 打包、Docker clean-host 构建和版本发布。
- 增加 SQLite 备份恢复、日志脱敏、配置诊断和升级迁移。
- 用真实 Provider、MCP、Web 访问和本地 workspace 做验收。
- 增加压力、故障恢复和安全测试。

验收：新机器可按文档安装；升级不会丢失任务、记忆和产物；失败时有可恢复路径。

## 14. 验收标准

### 产品验收

- 用户能创建并配置 Kevin。
- 用户能在 Web 中发起即时对话和长期任务。
- Kevin 能读取 workspace、执行受限工具并生成产物。
- 用户能看到当前状态、活动和等待原因。
- 高风险动作能被批准、拒绝、暂停和重试。
- 任务能在进程重启后恢复。
- 用户能保存、修改和删除记忆。
- 连接器能单独启用、限制范围和撤销。

### 工程验收

- TypeScript 类型检查通过。
- Core、Host、DB、Policy、Provider、Connector 单元测试通过。
- Web E2E 覆盖 Chat、Task、Approval、Activity、Settings。
- 数据库 migration、导入、备份和恢复测试通过。
- Docker 在无本地缓存的 clean host 构建通过。
- 真实 Provider 至少完成一次成功、超时、限流、鉴权失败和错误恢复测试。
- 日志和诊断包不包含 API key、Cookie、Token 或私密文件内容。

### 发布验收

- `kevin --version`、`kevin doctor` 和 `kevin init` 可用。
- README、中文文档、配置示例和截图与实际功能一致。
- 有 CHANGELOG、SECURITY、CONTRIBUTING 和许可证。
- GitHub Release 可安装、可升级、可回滚。
- 公开仓库不包含用户状态数据库、日志、凭据、构建产物和本地 IDE 文件。

## 15. 当前仓库的具体调整清单

### 立即调整

- 将项目显示名称从 `Agents` 改为 `Kevin`。
- 将 `package.json` 和 workspace 包名改为 `@kevin/*`。
- 将 `AGENTS_*` 配置前缀逐步迁移为 `KEVIN_*`，保留一个版本周期的兼容读取。
- 更新 `config/defaults.toml` 中的产品名、状态路径和默认工具策略。
- 修正 `docs/features.md`：源码已有远多于 read/list 的工具，文档必须以 registry 为准。
- 增加 `docs/product.md`、`docs/security.md`、`docs/self-hosting.md`。
- 清理公开仓库中的 `.agents` 运行状态、日志、`.venv`、`dist` 和 IDE 文件。
- 检查已被 Git 跟踪的构建产物（当前 `apps/web/dist/` 仍在跟踪范围内），决定是发布静态资源还是改为 CI 产物；不能只依赖 `.gitignore`。

### 后续调整

- 把 `JsonStateStore` 替换为 `Store` interface + SQLite adapter。
- 将 scheduler、worker、artifact、approval 从混合 host service 中拆出明确模块。
- 把 team/collaboration 能力移出 Kevin 默认产品面。
- 统一事件 schema，Web、Terminal、SDK 只消费同一份 protocol-neutral event。
- 增加数据库迁移和 clean-host 发布流水线。

## 16. 最终产品判断

Kevin 的差异化不应是“拥有最多工具”，而应是：

> **一个真正记得上下文、拥有自己的工作空间、会持续推进目标、关键时刻会征求同意、所有动作都可以被看见和恢复的个人 Agent。**

当前项目适合作为 Kevin 的 runtime 基础，但还需要数据库、长期任务、连接器权限、活动中心和产品化仓库治理，才能从“Agent 工程项目”变成“可宣传和分发的 Agent 产品”。
