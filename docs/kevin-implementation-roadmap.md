# Kevin 实施规划与交付计划

> 版本：v1.0
> 日期：2026-10-23
> 目标：将当前 `Agents` TypeScript runtime 演进为一个本地优先、可云化的个人长期运行 Agent，产品名为 Kevin。
> 关联方案：[Kevin 产品与架构规划](/Users/berhand/program/Personal/Pixeldooooog/Agents/Agents/docs/kevin-product-architecture-plan.md)

## 1. 交付目标

最终交付物不是一个“带聊天页面的工具调用器”，而是一个具备以下闭环的产品：

```text
创建 Kevin
  -> 配置模型、工作空间和权限
  -> 发起对话或长期任务
  -> Agent 在受限执行环境中工作
  -> 记录每一步活动和中间状态
  -> 遇到高风险动作请求审批
  -> 生成文件、报告、补丁或链接
  -> 用户查看、修改、继续或回滚
  -> 服务重启后任务仍可恢复
```

产品路线采用三层架构：

```text
Kevin Client       Web / Terminal / Desktop later
Kevin Control      API / Auth / Task / Memory / Approval / Activity
Kevin Execution    Local Worker now / Cloud Sandbox later
```

第一阶段不实现完整的云服务，但所有核心接口必须能在未来替换本地执行器和 SQLite，而不重写 Agent domain。

## 2. 当前基线与目标差距

### 已有并保留

- `packages/core`：模型调用、工具注册、runtime loop、权限、session、task、schedule、MCP 和 SDK。
- `packages/host`：Bun HTTP host、Terminal host、API route。
- `apps/web`：Solid/Vite Web UI。
- `apps/terminal`：Ink Terminal UI。
- 多模型 profile 和 protocol-neutral runtime events。
- 文件、搜索、Patch、Git、Shell、Web、MCP、Memory、Planning、Workflow 等工具。
- 本地类型检查、测试和 UI smoke。

### 必须重构或补齐

- `JsonStateStore` → Store contract + SQLite adapter。
- 单进程 Task Service → 可恢复的 queue/worker/checkpoint。
- 字符串 `enabled_tools` → 结构化 capability/policy。
- 混合 API route → 明确的 application service 和 domain service。
- 当前 Web UI → Kevin 产品界面和活动中心。
- `Agents` 命名 → `Kevin` 命令、包名、配置前缀和文档。
- 现有团队/多 Agent 能力 → 隐藏在默认产品面之外，暂不作为核心路线。
- 运行状态、日志和本地脏文件 → 完整的发布仓库清理策略。

## 3. 目标仓库结构

```text
kevin-agent/
  apps/
    web/                         Solid Web client
    terminal/                    Ink CLI client
  packages/
    core/                        Agent domain and run loop
    host/                        HTTP/SSE/WebSocket application host
    db/                          Store interfaces, SQLite, migrations
    config/                      Typed config and secret redaction
    policy/                      Capability and approval engine
    workspace/                   Workspace, file index, artifact store
    providers/                   Model provider adapters
    connectors/                  MCP and external app connectors
    scheduler/                   Queue, worker, retry, checkpoint
    observability/               Event schema, trace, metrics, diagnostics
  migrations/                    SQL migration files
  config/
    defaults.toml
    examples/
  deploy/
    Dockerfile
    docker-compose.yml
    compose.dev.yml
  docs/
    product.md
    architecture.md
    configuration.md
    security.md
    self-hosting.md
    connectors.md
    contributing.md
    adr/
  examples/
    minimal/
    developer/
  scripts/
  .github/
    workflows/
    ISSUE_TEMPLATE/
  README.md
  README.zh-CN.md
  CHANGELOG.md
  SECURITY.md
  CONTRIBUTING.md
  LICENSE
```

目录边界要求：

- `core` 不导入具体数据库、HTTP、React/Solid、Bun API。
- `db` 只实现数据存取和 migration，不实现 Agent 决策。
- `host` 只负责请求解析、认证、服务编排和响应投影。
- `policy` 是所有工具、Connector、Workspace 写入的统一授权入口。
- `scheduler` 只负责任务调度和恢复，具体 Agent 行为仍由 `core` 执行。
- UI 只消费 API 和事件，不复制 runtime 状态机。

## 4. 核心领域模型

### 4.1 Agent

```ts
interface AgentProfile {
  id: string;
  slug: string;
  name: string;
  avatar?: string;
  description?: string;
  systemPrompt: string;
  timezone: string;
  defaultModelProfile: string;
  status: "active" | "paused";
  createdAt: string;
  updatedAt: string;
}
```

第一版本只有一个默认 Agent，数据库仍保留 `agent_id`，避免未来改表。

### 4.2 Task 与 Run

```ts
interface AgentTask {
  id: string;
  agentId: string;
  workspaceId: string;
  title: string;
  goal: string;
  mode: "chat" | "task" | "review" | "scheduled";
  status: "queued" | "running" | "waiting_input" | "waiting_approval" |
    "paused" | "completed" | "failed" | "cancelled";
  nextRunAt?: string;
  createdAt: string;
  updatedAt: string;
}

interface AgentRun {
  id: string;
  taskId?: string;
  conversationId?: string;
  requestId: string;
  status: RunStatus;
  attempt: number;
  checkpointVersion: number;
  modelProfile: string;
  startedAt?: string;
  finishedAt?: string;
  errorCode?: string;
}
```

规则：

- Task 表示用户目标，Run 表示一次执行尝试。
- Run 必须有幂等 `request_id`。
- 每次工具调用都必须关联 Run 和 Event。
- 任务可以有多个 Run，但同一时刻只能有一个 active Run。
- 取消 Task 必须传播到 active Run、子进程和等待队列。

### 4.3 Event

统一事件格式：

```ts
interface KevinEvent {
  id: string;
  runId?: string;
  taskId?: string;
  sequence: number;
  type:
    | "run.created" | "run.started" | "run.paused" | "run.completed"
    | "run.failed" | "model.message" | "tool.started" | "tool.completed"
    | "approval.requested" | "approval.decided" | "artifact.created"
    | "user.input_required" | "checkpoint.saved";
  actor: "user" | "kevin" | "tool" | "system";
  payload: Record<string, unknown>;
  createdAt: string;
}
```

Event 是事实记录，UI 的状态是由 Event 和当前实体状态投影出来的。任何状态变化都不能只改内存。

## 5. 数据库实施方案

### 5.1 技术选择

第一阶段使用 SQLite：

- 本地安装零依赖。
- 支持事务、索引、FTS5 和 WAL。
- 适合单用户、自托管和桌面应用。
- 通过 Store 接口保留 Postgres 适配器的可能性。

推荐实现：使用 Bun/TypeScript 可稳定使用的 SQLite 驱动，数据库初始化、事务和 migration 全部放在 `packages/db`。具体驱动在实现阶段根据 Bun 版本验证后固定，不在业务代码中直接暴露驱动类型。

### 5.2 表与约束

```sql
agents(id TEXT PRIMARY KEY, slug TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  system_prompt TEXT NOT NULL, timezone TEXT NOT NULL,
  default_model_profile TEXT NOT NULL, status TEXT NOT NULL,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);

workspaces(id TEXT PRIMARY KEY, agent_id TEXT NOT NULL REFERENCES agents(id),
  name TEXT NOT NULL, root_path TEXT NOT NULL, policy_json TEXT NOT NULL,
  status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);

conversations(id TEXT PRIMARY KEY, agent_id TEXT NOT NULL REFERENCES agents(id),
  workspace_id TEXT REFERENCES workspaces(id), title TEXT NOT NULL,
  status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);

messages(id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id),
  role TEXT NOT NULL, content_json TEXT NOT NULL, sequence INTEGER NOT NULL,
  created_at TEXT NOT NULL, UNIQUE(conversation_id, sequence));

tasks(id TEXT PRIMARY KEY, agent_id TEXT NOT NULL REFERENCES agents(id),
  workspace_id TEXT NOT NULL REFERENCES workspaces(id), conversation_id TEXT,
  title TEXT NOT NULL, goal TEXT NOT NULL, mode TEXT NOT NULL,
  status TEXT NOT NULL, next_run_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);

runs(id TEXT PRIMARY KEY, task_id TEXT REFERENCES tasks(id), conversation_id TEXT,
  request_id TEXT UNIQUE NOT NULL, status TEXT NOT NULL, attempt INTEGER NOT NULL,
  checkpoint_version INTEGER NOT NULL, model_profile TEXT NOT NULL,
  checkpoint_json TEXT, started_at TEXT, finished_at TEXT, error_code TEXT);

events(id TEXT PRIMARY KEY, run_id TEXT REFERENCES runs(id), task_id TEXT REFERENCES tasks(id),
  sequence INTEGER NOT NULL, type TEXT NOT NULL, actor TEXT NOT NULL,
  payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(run_id, sequence));

approvals(id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
  tool_call_id TEXT NOT NULL, action_summary TEXT NOT NULL, risk TEXT NOT NULL,
  status TEXT NOT NULL, requested_at TEXT NOT NULL, decided_at TEXT,
  decided_by TEXT, decision_reason TEXT);

tool_calls(id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
  name TEXT NOT NULL, arguments_json TEXT NOT NULL, result_json TEXT,
  status TEXT NOT NULL, risk TEXT NOT NULL, started_at TEXT, finished_at TEXT);

memories(id TEXT PRIMARY KEY, agent_id TEXT NOT NULL REFERENCES agents(id),
  workspace_id TEXT, kind TEXT NOT NULL, content TEXT NOT NULL,
  source TEXT NOT NULL, confidence REAL, created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL, expires_at TEXT);

artifacts(id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
  workspace_id TEXT NOT NULL REFERENCES workspaces(id), type TEXT NOT NULL,
  name TEXT NOT NULL, path TEXT NOT NULL, mime_type TEXT, sha256 TEXT NOT NULL,
  metadata_json TEXT, created_at TEXT NOT NULL);

connectors(id TEXT PRIMARY KEY, agent_id TEXT NOT NULL REFERENCES agents(id),
  type TEXT NOT NULL, name TEXT NOT NULL, status TEXT NOT NULL,
  config_json TEXT NOT NULL, secret_ref TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);

connector_permissions(id TEXT PRIMARY KEY, connector_id TEXT NOT NULL REFERENCES connectors(id),
  capability TEXT NOT NULL, resource_scope TEXT NOT NULL, mode TEXT NOT NULL,
  expires_at TEXT);

usage_records(id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
  provider TEXT NOT NULL, model TEXT NOT NULL, input_tokens INTEGER,
  output_tokens INTEGER, cost_usd REAL, created_at TEXT NOT NULL);
```

### 5.3 数据保护

- `payload_json` 中的 token、Cookie、Authorization、私钥和环境变量必须在写库前脱敏。
- 大文件只存 artifact metadata，内容进入文件系统或对象存储。
- 数据库使用 WAL；写事务必须短，不能在事务内等待模型或工具。
- 每次升级前自动备份数据库和 migration 版本。
- `kevin export` 导出可迁移数据；`kevin import` 只能导入显式选择的备份。

## 6. API 设计

API 前缀统一为 `/api/v1`，响应统一包含 `request_id`。

### Agent 和配置

```text
GET    /api/v1/agent
PATCH  /api/v1/agent
GET    /api/v1/model-profiles
GET    /api/v1/settings
PATCH  /api/v1/settings
POST   /api/v1/doctor
```

### Conversation

```text
GET    /api/v1/conversations
POST   /api/v1/conversations
GET    /api/v1/conversations/:id
POST   /api/v1/conversations/:id/messages
GET    /api/v1/conversations/:id/events   # SSE
```

### Tasks

```text
GET    /api/v1/tasks
POST   /api/v1/tasks
GET    /api/v1/tasks/:id
POST   /api/v1/tasks/:id/run
POST   /api/v1/tasks/:id/pause
POST   /api/v1/tasks/:id/resume
POST   /api/v1/tasks/:id/cancel
GET    /api/v1/tasks/:id/events          # SSE
```

### Approvals 和 Artifacts

```text
GET    /api/v1/approvals?status=pending
POST   /api/v1/approvals/:id/approve
POST   /api/v1/approvals/:id/deny
GET    /api/v1/runs/:id/artifacts
GET    /api/v1/artifacts/:id/download
```

### Memory、Workspace、Connector

```text
GET    /api/v1/memories
POST   /api/v1/memories
PATCH  /api/v1/memories/:id
DELETE /api/v1/memories/:id
GET    /api/v1/workspaces
POST   /api/v1/workspaces
GET    /api/v1/connectors
POST   /api/v1/connectors/:id/enable
POST   /api/v1/connectors/:id/disable
POST   /api/v1/connectors/:id/revoke
```

API 层只解析输入和调用 application service。不要把数据库查询和 runtime 分支直接写进 route 文件。

## 7. Policy 与安全模型

### 7.1 Capability

每个工具和连接器声明：

```ts
interface Capability {
  id: string;
  action: string;
  resource: string;
  mode: "read" | "write" | "execute" | "send";
  risk: "low" | "medium" | "high" | "critical";
  approval: "never" | "once" | "always" | "disabled";
}
```

### 7.2 默认策略

| 能力 | 默认行为 |
|---|---|
| 读 workspace | 允许，但受路径范围限制 |
| 搜索 Web | 允许，记录域名和请求 |
| 写文件/Patch | 首次或每次确认，可按 workspace 记住 |
| Shell | 默认关闭，启用后限制命令、目录和时间 |
| 删除文件 | 每次确认 |
| Git commit | 每次确认 |
| Git push | 默认禁止，显式启用后每次确认 |
| 外部发送消息 | 每次确认 |
| 读取密钥/Cookie | 禁止 |
| 本地电脑控制 | 默认关闭，连接后逐能力授权 |

### 7.3 Sandbox

Local worker 至少实现：

- 工作目录 allowlist。
- 子进程超时和取消。
- 命令 allowlist/denylist。
- 网络开关。
- 最大输出和最大文件大小。
- 进程树清理。
- 每次执行生成 sandbox metadata。

Cloud worker 后续改为隔离 VM 或容器，但不能把本地 worker 的安全检查删除。

## 8. Scheduler、Worker 与恢复

### 8.1 组件

```text
TaskRepository
  -> Queue
  -> SchedulerLeader
  -> RunWorker
  -> AgentRuntime
  -> CheckpointStore
  -> EventProjector
```

第一阶段单进程运行，但仍以队列和 worker 接口组织；第二阶段可将 Queue 替换为 Redis、Postgres 或托管队列。

### 8.2 状态和锁

- `queued` 任务由 scheduler 取出，写入 lease。
- lease 包含 `worker_id`、`lease_until`、`heartbeat_at`。
- worker 每隔固定时间更新 heartbeat。
- lease 过期后任务可重新排队，但必须检查幂等 key。
- active Run 只能由一个有效 lease 执行。
- 外部不可逆动作必须使用 approval token，避免重试重复发送。

### 8.3 Checkpoint

Checkpoint 至少包含：

- conversation message cursor。
- 已完成 tool call IDs。
- 当前 plan step。
- pending approval/input。
- context summary。
- 已生成 artifact IDs。
- retry counters。

每完成一个工具或审批决策就保存 checkpoint。模型调用过程中不保存半成品，避免恢复出错。

## 9. Web 产品实施

### 9.1 页面优先级

1. Today：正在进行、需要处理、最近结果。
2. Chat：对话和即时任务。
3. Tasks：后台任务列表、状态、暂停和恢复。
4. Activity：完整事件时间线和诊断。
5. Connections：模型、MCP、文件和本地电脑授权。
6. Memory：查看、编辑和删除长期记忆。
7. Workspace：目录、Git 状态、产物。
8. Settings：Agent 身份、策略、通知、数据和升级。

### 9.2 关键交互

- 首页始终显示 Kevin 当前状态：Idle、Working、Waiting、Paused、Error。
- 用户发送消息时明确选择 Chat 或 Task；不要让系统猜长期任务。
- 审批卡片显示：动作、目标、风险、原因、允许范围、一次性/记住选择。
- 工具活动默认显示自然语言摘要，点击后再显示参数和原始结果。
- 任务详情页支持“追加指令”，追加内容形成新的 user event，不覆盖原始目标。
- 失败页必须提供 Retry、Edit task、View activity、Cancel 四个明确动作。
- 产物卡片支持预览、下载、打开所在目录和回到生成 Run。

### 9.3 视觉验收

- 首屏在 1440px 和 1280px 宽度下不出现横向滚动。
- 页面采用浅色和深色主题，但状态颜色含义一致。
- 键盘可完成发送、审批、暂停和关闭抽屉。
- 流式事件不会导致消息列表跳动。
- 长日志、Diff 和 JSON 都使用折叠和虚拟滚动。
- 空状态必须提供可点击示例任务。

## 10. CLI 与桌面路线

### CLI 命令

```text
kevin init
kevin start
kevin chat
kevin task create "..."
kevin task list
kevin task pause <id>
kevin task resume <id>
kevin approval list
kevin approval approve <id>
kevin activity <run-id>
kevin connect list
kevin doctor
kevin export <file>
kevin import <file>
```

### Desktop

桌面应用放到第二阶段，不先引入复杂 Electron/Tauri 运行时。第一阶段用 Web + local host 验证产品行为。桌面应用只负责：

- 启动和管理 local host。
- 展示 Web UI。
- 管理本地 Bridge 权限。
- 提供系统通知和开机启动。

不要在桌面壳里复制 Agent runtime。

## 11. 分阶段实施

### Phase 0：命名和产品基线（1 周）

交付：

- `Agents` → `Kevin` 的品牌和目录命名方案。
- `docs/product.md`、`docs/security.md`、`docs/self-hosting.md`。
- 工具和能力矩阵。
- 单 Agent ADR。
- 清理公开仓库中的运行时数据库、日志、虚拟环境、dist 和 IDE 文件。

验收：

- README 首屏能解释 Kevin 是什么。
- 默认界面不暴露 team/multi-agent。
- CI 不依赖旧 Python 文件或旧命令。

### Phase 1：Store 抽象和 SQLite（2 周）

任务：

- 新建 `packages/db`。
- 定义 `AgentStore`、`RunStore`、`TaskStore`、`EventStore`、`ArtifactStore` 接口。
- 新增 migration runner、schema version 和 WAL。
- 实现 JSON importer 和备份。
- 将 core/host 从 `JsonStateStore` 依赖改为接口依赖。
- 增加并发写、事务回滚和导入测试。

验收：

- 现有 185 个测试继续通过。
- 新进程能读取 SQLite 中的 Run/Task/Event。
- JSON 导入后任务、事件和 session 可查询。
- 数据库升级失败时有备份和明确错误。

### Phase 2：Durable Run 和 Scheduler（3 周）

任务：

- 引入 queue、lease、heartbeat 和 worker。
- 将 Task Service 改为可恢复状态机。
- 保存 checkpoint。
- 支持 pause、resume、cancel、retry。
- 增加 scheduler 和 schedule lock。
- 记录 usage 和预算。

验收：

- 运行中杀掉进程，重启后任务能继续。
- 重复提交同一 request 不会产生重复 Run。
- 工具失败按策略重试，业务错误不会无限重试。
- 任务超时、成本超限和工具次数超限都会进入可解释状态。

### Phase 3：Policy、Approval 和 Workspace（3 周）

任务：

- 将权限拆为 capability、scope、risk、approval。
- 将所有写工具接入 Policy Engine。
- 增加 Workspace allowlist 和 shell sandbox。
- 完善审批 API、审批事件和审批历史。
- 增加 artifact manager、hash 和下载接口。

验收：

- 没有 Policy 的工具不能执行。
- 拒绝审批后工具不执行且 Run 可恢复。
- 删除、发送、push 等高风险动作每次都能拦截。
- 产物可以预览、下载和与 Run 关联。

### Phase 4：Kevin Web（3 周）

任务：

- 重做 Today、Chat、Tasks、Activity。
- 增加 Approval Center、Artifacts 和 Memory 页面。
- SSE/WebSocket 统一事件投影。
- 处理断线重连、事件去重和分页。
- 增加可访问性、键盘操作和响应式布局。

验收：

- 只用 Web 完成创建任务、批准动作、查看结果、暂停和恢复。
- 刷新页面不会丢失活动或重复渲染事件。
- Web 的状态和 Terminal 的状态一致。
- 失败 Run 能从 Activity 页面定位原因并重试。

### Phase 5：连接器和 Local Bridge（3 周）

任务：

- 定义 Connector interface。
- 将 MCP、Git、Web、Filesystem 接入 Connector。
- 增加 connector permissions 和 revoke。
- 新建 `packages/bridge`，只负责本地受控执行。
- Bridge 与 Host 之间使用短期 token、设备 ID 和显式 pairing。

验收：

- 每个连接器都有独立 scope。
- revoke 后已有 Run 不能继续调用该能力。
- Bridge 断线后云端任务进入 waiting/retry，而不是假装成功。
- 本地文件路径不会超出授权根目录。

### Phase 6：分发与自托管（2 周）

任务：

- `kevin init/start/doctor/export/import`。
- Bun 编译或 npm package 发布方式固定。
- Docker clean-host 构建和 compose。
- 数据目录、备份、升级和回滚脚本。
- GitHub Release、CHANGELOG、SECURITY、CONTRIBUTING。
- 截图、演示数据和安装文档。

验收：

- 新机器按 README 在 15 分钟内完成启动。
- 升级不丢数据库、记忆、任务和产物。
- `kevin doctor` 能指出模型、数据库、端口、权限和 workspace 问题。
- Docker 在无本地缓存环境构建成功。

### Phase 7：Cloud Worker（后续）

任务：

- 将 Worker 接入隔离容器或 VM。
- 抽象对象存储和 Hosted Store。
- 增加 worker pool、配额、租约和远程日志。
- Web、Local Worker、Cloud Worker 共用同一 Agent event contract。
- 对本地文件访问全部改为 Local Bridge 能力。

验收：

- 云端任务在关闭客户端后继续运行。
- 每个用户/Agent 的执行环境隔离。
- 云端不能默认读取本地电脑。
- 云端任务可以暂停、查看、审批和恢复。

## 12. 测试策略

### 单元测试

- Run 状态机的每个状态转换。
- Policy decision 和 scope matching。
- Store transaction、migration、backup、import。
- Queue lease、heartbeat、retry、dedupe。
- Event sequence 和 replay。
- Artifact hash、path validation、redaction。

### 集成测试

- Core + SQLite。
- Host API + SQLite。
- Scheduler + Worker + fake model。
- Approval + tool executor。
- Connector revoke + active Run。
- SSE/WebSocket 断线重连。

### E2E

至少覆盖：

1. 初始化 Kevin。
2. 配置 fake provider。
3. 发起 Chat。
4. 创建后台 Task。
5. Task 触发写文件审批。
6. 用户批准并生成 Artifact。
7. 进程重启后查看结果。
8. 用户暂停、恢复、取消任务。
9. 导出并导入数据。

### 外部环境验收

本地测试不能替代：

- 真实 OpenAI/Anthropic/Gemini 请求。
- 真实 MCP Server。
- Docker clean-host。
- 网络超时、限流、鉴权失败。
- 大文件和长任务。
- 多客户端并发连接。
- 备份恢复和磁盘不足。

## 13. 观测与诊断

最小指标：

- active runs、queued tasks、waiting approvals。
- Run latency、tool latency、model latency。
- token usage、estimated cost。
- retry count、failure rate、cancel rate。
- connector health、worker heartbeat。
- database size、artifact size、event lag。

日志要求：

- 每条日志带 `request_id`、`run_id`、`task_id`。
- 生产默认不打印 prompt、完整 tool arguments 和文件内容。
- `kevin doctor --redact` 输出可分享诊断包。
- 用户可从 Activity 页面定位 Event ID，再从日志查找对应执行链。

## 14. 风险与取舍

| 风险 | 应对 |
|---|---|
| 一开始做云端导致范围失控 | 先做 Local Worker，接口先云化 |
| SQLite 并发不足 | 单进程本地模式使用 SQLite；远程模式切 Postgres |
| Agent 自主执行产生不可逆副作用 | capability + scope + approval + deny-by-default |
| 多 Agent 功能拖慢产品收敛 | 默认隐藏，移到实验包 |
| UI 和 runtime 状态不一致 | 统一 Event schema 和 projection |
| 数据迁移破坏用户状态 | 导入前备份、版本化 migration、可回滚 |
| Provider 行为不稳定 | fake provider + contract test + 真实 provider smoke |
| Cloud 与 Local 权限混淆 | Cloud Worker 和 Local Bridge 使用不同 capability namespace |
| 公开仓库泄露个人数据 | `.gitignore`、发布检查、secret scan、clean-host CI |

## 15. 发布门禁

每个 Release 必须通过：

```text
[ ] git status clean
[ ] tracked Python/runtime legacy files = 0
[ ] typecheck passed
[ ] unit/integration tests passed
[ ] Web build passed
[ ] E2E smoke passed
[ ] migration upgrade/rollback passed
[ ] Docker clean-host build passed
[ ] secret scan passed
[ ] README and screenshots match current UI
[ ] CHANGELOG and version updated
[ ] backup/restore tested
[ ] real provider smoke recorded
```

本地测试通过不能直接宣称生产可用。真实 Provider、Docker、签名、部署和故障恢复必须分别记录结果。

## 16. 第一批开发任务

按依赖顺序，第一批不要同时重做 UI 和云端：

1. 创建 `kevin` 命名迁移 ADR。
2. 清理仓库状态文件、日志和旧构建产物。
3. 新建 `packages/db` 和 Store interfaces。
4. 实现 SQLite schema v1：agents、workspaces、conversations、messages、tasks、runs、events、approvals、artifacts。
5. 给现有 JSON store 增加导入器。
6. 把 `AgentRunService`、`TaskService` 改为依赖 Store interfaces。
7. 增加 Run checkpoint 和事件重放测试。
8. 重写 `docs/features.md`，以实际 tool registry 为准。
9. 将现有 team/collaboration 从默认工具集和 UI 隐藏。
10. 建立 Today/Tasks/Activity 的 UI 骨架。

第一批完成后再进入 Scheduler。若 Store 抽象没有稳定，后续所有任务都可能重复返工。

## 17. 完成定义

Kevin v1 的完成定义：

- 用户可以在本地安装和启动 Kevin。
- Kevin 具有持久身份、workspace、记忆和配置。
- 用户可以创建 Chat 和 Task。
- Task 可以后台运行、暂停、恢复、取消和重试。
- 所有工具动作都有 Policy 判断和 Event 记录。
- 高风险动作必须审批。
- 任务和事件存储在 SQLite，并能在重启后恢复。
- Web 可以查看 Today、Chat、Tasks、Activity、Approvals 和 Artifacts。
- Terminal 可以完成诊断和恢复操作。
- 数据可以备份、导出、导入和升级。
- 仓库以 Kevin 名称公开分发，文档、脚本、截图和实际行为一致。

达到这个定义后，Kevin 才从“Agent runtime 工程”变成一个真正可使用、可展示、可继续云化的个人 Agent 产品。
