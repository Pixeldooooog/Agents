# Kevin 实施规划与交付计划

> 版本：v1.2（基线先行，产品分层）
> 日期：2026-10-26
> 目标：将当前 `Agents` TypeScript runtime 演进为一个本地优先、可云化的个人长期运行 Agent，产品名为 Kevin。
> 关联方案：[Agent 系统基线设计与验收矩阵](agent-system-baseline.md)、[Kevin 产品与架构规划](kevin-product-architecture-plan.md)
> 优先级：系统契约和基线完成定义以基线文档为准；本文件中的 SQL/API 示例在 B0 转为正式契约前属于设计输入。

## 0. 复核结论、假设和边界

这份文档是目标设计和实施顺序，不代表目标能力已经存在。当前仓库仍是 `Agents` 命名、JSON state store、单进程任务执行和本地 host；只有完成对应阶段并通过验收，才可以把某项能力写成 Kevin 已支持的功能。

本计划采用以下经过复核的假设：

- v1 是单用户、本地优先产品；`agent_id` 保留在数据模型中是兼容性设计，不等于 v1 已支持多租户。
- v1 的“后台任务”是本机进程可恢复任务；在没有 Cloud Worker 之前，不宣称关闭电脑后仍会运行。
- 云端路线是后续架构兼容目标，不能用本地测试替代云端隔离、密钥、网络和可靠性验收。
- 实施顺序调整为 B0–B3 系统基线、P1–P3 个人产品、C1 云端执行。旧 Phase 周数撤下；B0 技术验证和验收矩阵冻结后重新估算，包含验证与返工。
- SQLite 首选 bun:sqlite，CLI 采用 Bun compile + GitHub Release + 自有 Homebrew tap；具体版本、平台兼容性和隔离后端经 spike 后锁定 ADR。云供应商后续确定；Memory 以 Markdown 为事实源，不引入向量数据库。

本次复核识别出的强制修正是：

1. 将租约、调度、幂等、通知和 schema 版本纳入持久化模型。
2. 为 API 补上认证、分页、幂等、错误 envelope 和 SSE 断线重连约定。
3. 将本地 host 的安全默认值从“开放监听/无限工具循环”调整为“本地监听/有限预算”，远程暴露必须显式配置。
4. 增加 prompt injection、SSRF、凭据、数据删除和备份恢复的验收项。
5. 明确 Cloud Control Plane、Cloud Worker 和 Local Bridge 的信任边界。

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

产品路线采用分层架构：

```text
Kevin Client       Web / Terminal / Desktop later
Personal Services  Identity / Project / Goal / Plan / Routine / Attention
Agent Baseline     Kernel / Execution / Context / Policy / Storage contracts
Adapters           Model / Connector / SQLite / Files / Local or Cloud Worker
```

B/P 阶段不实现完整的云服务，但所有核心接口必须能在未来替换本地执行器和 SQLite，而不重写 Agent domain。`core` 不应知道“云端”或“本地”的差别；执行位置由 Worker adapter 和 capability policy 决定。

### 1.1 三个信任域

```text
Control Plane
  Agent profile / conversation / task / policy / approval / event metadata

Execution Plane
  model call / filesystem / shell / browser / MCP / artifact generation

User Device
  local files / local apps / browser sessions / Kevin Bridge
```

- Control Plane 可以调度执行，但不能因为任务来自云端就自动获得本地文件权限。
- Execution Plane 只能使用被 Policy Engine 授予的 capability 和 resource scope。
- User Device 通过 Local Bridge 主动配对；Bridge 断开、过期或撤销后，相关能力立即失败关闭。
- Cloud Worker 与 Local Worker 使用同一 Run/Event contract，但不共享隐式凭据、文件路径或网络信任。

### 1.2 云端目标形态

Cloud Worker 阶段的最小生产拓扑应明确为：

```text
Client -> API/Auth -> Control DB (Postgres)
                    -> Queue/Scheduler
                    -> Isolated Worker VM/Container
                    -> Object Storage (artifacts)
                    -> Secret Manager (provider/connector secrets)
                    -> Metrics/Logs/Trace
Local Bridge <------ signed, scoped, short-lived capability token
```

在没有 Postgres、队列、隔离 Worker、对象存储和 Secret Manager 之前，Kevin 只能被称为本地/自托管版本，不能把“云端长期运行”列为当前产品能力。

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
apps/
  web/                 产品客户端
  terminal/            开发与诊断客户端
packages/
  core/                运行语义、消息/动作契约、上下文、ports
  execution/           协调、调度、lease、恢复、输入队列、预算
  personal/            身份、Project、Goal、Plan、Routine、通知
  storage/             SQLite、migrations、Markdown、产物与备份
  providers/           模型适配
  connectors/          外部能力适配
  executors/           受限进程、设备和远程 Worker
  host/                常驻服务、API、事件传输、认证和组装
```

依赖方向和所有权以 [基线第 3 节](agent-system-baseline.md#3-系统分层与所有权) 为准。core 不导入具体 SQL、HTTP、UI 或宿主执行实现；personal 不绕过 execution 执行工具。CLI/Web/Terminal 连接同一个本地状态与调度所有者。先解耦接口，按职责逐批迁移，不以目录搬迁代替行为验收。

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

type RunStatus = "queued" | "preparing" | "running" | "waiting_input" |
  "waiting_approval" | "paused" | "reconciling" | "completed" | "failed" |
  "cancelled" | "expired";

interface AgentRun {
  id: string;
  taskId?: string;
  conversationId?: string;
  requestId: string;
  status: RunStatus;
  workerAttempts: number; // 同一 Run 的执行接管次数；不是用户重试轮次
  checkpointVersion: number;
  modelProfile: string;
  startedAt?: string;
  finishedAt?: string;
  errorCode?: string;
}
```

规则：

- Goal 表示可选的长期目标；Task 是有边界的工作单元；Run 是一次可恢复逻辑执行。
- 进程恢复保持 Run ID，递增 lease epoch；新执行轮次创建新 Run，不自动重放此前 Action。
- Conversation、Project、Goal、版本化 Plan 和 Routine 的关系以基线第 4 节为准；长期 Plan 不绑定单个 Run。
- Run 必须有幂等 `request_id`。
- 每次工具调用都必须关联 Run 和 Event。
- 任务可以有多个 Run，但同一时刻只能有一个 active Run。
- 取消 Task 必须传播到 active Run、子进程和等待队列。

### 4.3 Event

统一事件格式：

```ts
interface KevinEvent {
  event_id: string;
  schema_version: number;
  runId?: string;
  taskId?: string;
  sequence?: number; // 有 runId 时必填；无 Run 的事件不借用 Run 序号
  type:
    | "run.created" | "run.started" | "run.paused" | "run.resumed"
    | "run.completed" | "run.failed" | "run.cancel_requested" | "run.cancelled" | "run.expired"
    | "run.waiting_input" | "run.waiting_approval" | "run.reconciling"
    | "model.message" | "tool.started" | "tool.completed"
    | "approval.requested" | "approval.decided" | "artifact.created"
    | "user.input_required" | "checkpoint.saved" | "task.updated"
    | "connector.changed" | "memory.changed"
    | "retention.started" | "retention.completed";
  actor: "user" | "kevin" | "tool" | "system";
  payload: Record<string, unknown>;
  occurred_at: string;
}
```

Event 是事实记录，UI 的状态是由 Event 和当前实体状态投影出来的。任何状态变化都不能只改内存。

Event schema 必须带 `schema_version`、`event_id` 和 `occurred_at`；`sequence` 只在同一个 Run 内有序。跨 Run、跨 Worker 的排序使用时间和 ID 作为展示排序，不能假设全局严格顺序。事件消费者必须支持重复投递，使用 `event_id` 去重。

## 5. 数据库实施方案

### 5.1 技术选择

本地基线使用 SQLite：

- 本地安装零依赖。
- 支持事务、索引、FTS5 和 WAL。
- 适合单用户、自托管和桌面应用。
- 通过 Store 接口保留 Postgres 适配器的可能性。

推荐实现：第一选择是 Bun 内置的 `bun:sqlite`，因为 Kevin 已经以 Bun 为运行时，可以减少原生依赖和安装问题。它提供 prepared statements、事务、WAL 和 foreign-key PRAGMA；事务回调必须保持同步，不能在事务内部 `await`。所有数据库操作封装在 `packages/storage`，业务层只依赖 Store 接口。

“SQLite 驱动是什么问题”不是 SQLite 不能用，而是驱动会影响：

- Bun 版本兼容性和跨平台发布包是否能直接运行。
- 事务 API 是否支持当前的同步/异步写法；错误地在事务中 `await` 可能让后续操作跑到事务外。
- WAL、foreign keys、busy timeout、文件锁和备份 API 的可控程度。
- 测试环境与用户环境的行为是否一致。

因此 B0 先选定候选 Bun 版本做一个 `packages/storage` spike：打开数据库、启用 WAL/foreign keys、执行 migration、并发读写、事务回滚、备份恢复和进程重启，然后把 Bun 版本与 `bun:sqlite` API 写进 ADR。若 spike 失败，再评估外部 SQLite driver；在 spike 之前不提前引入 ORM。

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
  request_id TEXT UNIQUE NOT NULL, status TEXT NOT NULL, worker_attempts INTEGER NOT NULL,
  checkpoint_version INTEGER NOT NULL, model_profile TEXT NOT NULL,
  checkpoint_json TEXT, started_at TEXT, finished_at TEXT, error_code TEXT);

events(event_id TEXT PRIMARY KEY, schema_version INTEGER NOT NULL,
  run_id TEXT REFERENCES runs(id), task_id TEXT REFERENCES tasks(id),
  sequence INTEGER, type TEXT NOT NULL, actor TEXT NOT NULL,
  payload_json TEXT NOT NULL, occurred_at TEXT NOT NULL,
  UNIQUE(run_id, sequence));

approvals(id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
  tool_call_id TEXT NOT NULL, action_summary TEXT NOT NULL, risk TEXT NOT NULL,
  status TEXT NOT NULL, requested_at TEXT NOT NULL, decided_at TEXT,
  decided_by TEXT, decision_reason TEXT);

tool_calls(id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
  name TEXT NOT NULL, arguments_json TEXT NOT NULL, result_json TEXT,
  status TEXT NOT NULL, risk TEXT NOT NULL, started_at TEXT, finished_at TEXT);

memories(id TEXT PRIMARY KEY, agent_id TEXT NOT NULL REFERENCES agents(id),
  workspace_id TEXT, kind TEXT NOT NULL, path TEXT NOT NULL,
  content_hash TEXT NOT NULL, source TEXT NOT NULL, confidence REAL,
  user_confirmed INTEGER NOT NULL, created_at TEXT NOT NULL,
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

run_leases(id TEXT PRIMARY KEY, run_id TEXT NOT NULL UNIQUE REFERENCES runs(id),
  worker_id TEXT NOT NULL, epoch INTEGER NOT NULL, lease_until TEXT NOT NULL, heartbeat_at TEXT NOT NULL,
  created_at TEXT NOT NULL);

schedules(id TEXT PRIMARY KEY, task_id TEXT NOT NULL UNIQUE REFERENCES tasks(id),
  expression TEXT NOT NULL, timezone TEXT NOT NULL, enabled INTEGER NOT NULL,
  next_run_at TEXT, last_run_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);

idempotency_keys(scope TEXT NOT NULL, key TEXT NOT NULL, request_hash TEXT NOT NULL,
  status TEXT NOT NULL, response_json TEXT,
  created_at TEXT NOT NULL, expires_at TEXT NOT NULL, PRIMARY KEY(scope, key));

notifications(id TEXT PRIMARY KEY, agent_id TEXT NOT NULL REFERENCES agents(id),
  task_id TEXT, type TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
  status TEXT NOT NULL, created_at TEXT NOT NULL, read_at TEXT);

schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL);
```

这些表是草案，尚未覆盖完整 Grant、Action Ledger、输入队列和 outbox；B0 必须补齐契约与事务边界，不能直接视为可执行 migration。生产 schema 还必须明确：

- 同一 Task 的 active Run 唯一约束、Run 状态版本检查与 lease epoch 校验。
- Action intent、结果、unknown 核对，以及同幂等键不同请求内容的冲突处理。

- 启用 SQLite foreign keys；删除 Agent/Workspace/Task 时使用显式归档或受控级联，不能依赖驱动默认值。
- `runs(request_id)`、`events(run_id, sequence)`、`tasks(status, next_run_at)`、`approvals(status, requested_at)`、`notifications(status, created_at)` 建立索引。
- `approval` 必须保存所批准的 capability、resource scope、参数摘要和策略版本，不能只保存一个布尔结果。
- `tool_calls` 要有稳定的 `tool_call_id`、幂等键和执行器版本，便于恢复和审计。
- `memories` 的来源、用户确认状态、过期时间和删除时间必须可追溯；模型自动推断的记忆不能默认等同于用户确认的事实。

### 5.3 数据保护

- `payload_json` 中的 token、Cookie、Authorization、私钥和环境变量必须在写库前脱敏。
- 大文件只存 artifact metadata，内容进入文件系统或对象存储。
- 数据库使用 WAL；写事务必须短，不能在事务内等待模型或工具。
- 每次升级前自动备份数据库和 migration 版本。
- `kevin export` 导出可迁移数据；`kevin import` 只能导入显式选择的备份。

### 5.4 身份、密钥和数据生命周期

本地 v1 也必须有最小身份边界：

- 默认只监听 `127.0.0.1`，默认 CORS 只允许同源；绑定 `0.0.0.0` 必须显式设置并要求 access token。
- 首次初始化生成随机本地 token，Web UI 通过同源 cookie 或短期 bearer token 访问；健康检查只暴露无敏感信息的状态。
- Provider API key 和 Connector credential 可以进入 SQLite，但只能以 AEAD 加密密文、nonce、key version 和 metadata 保存，不能保存明文。
- 加密主密钥不能和数据库放在同一个可复制文件里：本地优先放系统 keychain；无 keychain 时使用用户主动提供的 `KEVIN_DB_KEY`，并在 `doctor` 中明确提示这是降级保护。若把解密密钥也放进同一个数据库，拿到数据库文件的人就能解密，这不算有效的凭据保护。
- Cloud 版本使用 Secret Manager，Worker 只收到短期、最小范围的 secret reference；本地 SQLite 的凭据 schema 不应直接复用成云端明文配置。
- `export` 默认排除凭据、原始工具输出中的敏感字段和可选的大文件；导入前显示内容清单并要求用户确认。
- 支持按 Agent、Conversation、Task、Artifact 和 Memory 删除；删除操作写审计事件并清理对应文件。
- 定义默认保留期：事件、消息、日志、产物和通知分别可配置；过期清理必须是可暂停、可审计的后台任务。
- 本地数据库和备份文件使用文件权限保护；云端数据库、对象存储和备份必须加密并记录恢复演练。

### 5.4.1 事件保留策略

事件保留策略回答的是“哪些记录保留多久、在哪里保留、如何删除和恢复”，不是简单地定一个全局天数。建议 v1 本地默认：

| 数据 | 默认策略 | 原因 |
|---|---|---|
| Conversation/Message | 用户删除前保留 | 用户需要长期上下文 |
| Task/Run 元数据 | 用户删除前保留 | 任务历史和恢复依据 |
| 详细 Runtime Event | 90 天 | 支持 Activity 调试，控制数据库增长 |
| 原始 Tool 输出/Trace | 30 天，可按 Run 锁定 | 可能含大量或敏感内容 |
| Application log | 14 天、按大小轮转 | 日志不是用户工作记录 |
| Artifact 文件 | 用户删除前保留，可设容量配额 | 结果可能仍有价值 |
| Notification | 已读后 30 天，未读不自动删除 | 避免漏掉审批和失败提醒 |
| Markdown Memory | 用户删除前保留 | 用户明确管理的事实源 |
| Database backup | 最近 7 份或最近 30 天 | 支持升级和灾难恢复 |

清理任务必须先写 `retention.started`/`retention.completed` 审计事件，支持 dry-run、暂停和恢复；删除事件不能用普通 Event 证明已经删除，因为这会重新保留敏感内容，只保留删除对象类型、ID 哈希、时间和操作者。Cloud 版本可以因为成本、法规和租户策略配置不同保留期，但必须在 UI 和导出说明中明确。

### 5.5 Markdown Memory（已确定不使用向量）

Kevin v1 不引入 embedding、向量数据库或向量检索。Markdown 对个人 Agent 足够，优点是用户可读、可编辑、可导出、可审查，也不会额外引入 embedding 成本和删除一致性问题。

建议目录：

```text
~/.kevin/memory/
  profile.md       # 用户确认的长期偏好
  projects/
    <slug>.md      # 项目级上下文
  decisions/
    <date>-<slug>.md
  daily/
    <date>.md      # 可选的运行摘要
```

SQLite 只保存 `path`、`kind`、`content_hash`、`source`、`user_confirmed`、`updated_at` 和 `expires_at`，作为元数据索引和变更检测。上下文注入使用受限的关键词/路径选择和文件大小预算；读取 Markdown 后仍要经过 prompt/context 预算，不允许整目录无界注入。用户手工编辑文件后，`kevin doctor memory` 或启动时刷新哈希。

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

### 6.1 API 统一契约

所有写请求必须支持 `Idempotency-Key`，并在响应中返回 `request_id`。列表接口统一使用 cursor 分页，不能用不稳定的 offset 作为长任务活动流的唯一分页方式。

成功响应示例：

```json
{
  "ok": true,
  "request_id": "req_...",
  "data": {}
}
```

失败响应示例：

```json
{
  "ok": false,
  "request_id": "req_...",
  "error": {
    "code": "approval_required",
    "message": "human-readable message",
    "retryable": false,
    "details": {}
  }
}
```

SSE 必须支持 `Last-Event-ID`，客户端重连后从最后一个已确认事件继续；事件投影必须可重复执行。WebSocket 仅作为需要双向控制或高频流式交互的可选传输，不能让核心业务只存在于 WebSocket 路径。

认证和跨域规则必须在 API 设计中显式表达：本地同源访问、远程自托管 token/session、Cloud 用户认证属于不同部署 profile，不能使用一个“无 token 即全部放行”的默认实现覆盖所有场景。

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

2026-10-26 用户调整：原生沙箱后端暂缓上线，不阻塞其余内核建设。当前 LocalExecutor 明确为宿主执行；预留平台 executor 和策略接口，要求隔离时失败关闭。未来受限执行仍须满足 K06 的文件、网络、环境变量和进程边界。以下约束属于后续隔离后端验收，目录和命令 allowlist 本身不构成完整 Sandbox：

- 工作目录 allowlist。
- 子进程超时和取消。
- 命令 allowlist/denylist。
- 网络开关。
- 最大输出和最大文件大小。
- 进程树清理。
- 每次执行生成 sandbox metadata。

C1 的 Cloud Worker 独立验证容器或 VM 隔离，继续保留这些约束；本地原生隔离独立排期，不以云端容器验收代替。

### 7.4 不可信内容和网络安全

文件、网页、MCP 返回值、Git 内容和用户提供的文档都必须视为不可信数据。它们可以提供事实或输入，但不能自行改变 Policy、审批结果、系统提示词或 Connector scope。

- 对工具参数做 schema 校验、路径归一化和资源 scope 校验；禁止通过 `..`、符号链接或 URL 重定向逃逸。
- Web 工具执行 SSRF 防护：限制协议、解析后的 IP、私网地址、重定向次数和允许域名；DNS 解析结果要在连接前再次检查。
- Browser/Computer 工具隔离 Cookie、下载目录、剪贴板和登录态；敏感登录必须由用户在受控界面完成。
- 模型输出中的“忽略规则”“自动批准”“上传密钥”等指令只能当作普通文本，不能改变系统策略。
- Approval 在实际执行前重新计算 capability、scope、参数摘要和策略版本；审批后参数发生变化必须重新审批。
- 连接器返回的数据要限制大小、MIME、递归深度和可执行内容，避免恶意内容触发本地执行。
- 所有高风险执行都有可撤销的 kill switch；取消、过期、Bridge 断开和策略撤销均以 fail-closed 为准。

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

B2 本地服务使用单一调度所有者，以队列和 Worker 接口组织；C1 再选择远程队列并验证分布式协调。

### 8.2 状态和锁

- `queued` 任务由 scheduler 取出，写入 lease。
- lease 包含 `worker_id`、`epoch`、`lease_until`、`heartbeat_at`；结果提交和新动作 dispatch 都校验当前 epoch。
- worker 每隔固定时间更新 heartbeat。
- lease 过期后恢复同一 Run 并递增 epoch；先核对已 dispatched/unknown Action，确定后才能继续执行，无法确定则进入 reconciling，不能只检查请求幂等 key。
- active Run 只能由一个有效 lease 执行。
- approval token 证明授权；防重复依靠稳定 operation ID、提供方幂等或回执核对，审批本身不能保证只执行一次。

调度允许重复投递，动作是否重试由 replay safety 契约决定：只读、幂等、可查询回执、不可重复分别处理；每次 dispatch 仍需有效授权和必要的审批。不可确定的发送、发布、删除等 Action 标记 unknown，Run 进入 reconciling；先查询回执或人工核实，不能自动重放，不能宣传外部副作用 exactly-once。

`cancel` 先持久化 `run.cancel_requested` 控制事件并阻止新动作，再向 Worker 及工具/子进程树传播取消。存在结果不确定的外部 Action 时保持 reconciling，并显示“取消请求已发出，结果待确认”；核对完毕、执行已收敛后才根据实际结果进入终态并记录相应事件，不能提前写入 run.cancelled。

### 8.3 Checkpoint

Checkpoint 至少包含：

- conversation message cursor。
- 已完成 tool call IDs。
- 当前 plan step。
- pending approval/input。
- context summary。
- 已生成 artifact IDs。
- retry counters。

动作 dispatch 前保存 intent；确定结果后按事务边界保存结果、状态、checkpoint 和 outbox。工具已执行但结果未落盘时按基线规则核对，无法确定则进入 reconciling/unknown。长等待释放执行 lease，恢复时重新验证授权和预算。模型中间流式片段不能冒充可恢复的已完成动作。

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

桌面应用作为 P2 的可选产品载体。B 阶段用现有 Web/Terminal 验证基线；常驻服务、自启动策略和恢复由 B2 的 host 完成，不等待桌面壳。桌面应用只负责：

- 启动和管理 local host。
- 展示 Web UI。
- 管理本地 Bridge 权限。
- 提供系统通知和开机启动。

不要在桌面壳里复制 Agent runtime。

### 10.1 CLI 分发建议：Homebrew 是渠道，不是 CLI 实现

建议把 CLI 分成两层：

1. `@kevin/cli`：TypeScript 命令实现和可测试的命令 contract。
2. 发布产物：优先用 Bun compile 生成 macOS arm64、macOS x64、Linux x64 和 Linux arm64 的独立可执行文件；Node/Bun package 作为开发者 fallback。

Homebrew 适合作为 macOS 用户的首选安装渠道：

```text
brew tap pixeldooooog/kevin
brew install kevin
```

P3 首次发行使用自有 tap，Formula 指向 GitHub Release 的固定版本和 SHA256；不要一开始依赖 Homebrew core 的审核周期。等 CLI 稳定、版本和升级流程成熟后，再评估提交到 Homebrew core。Docker Compose 作为服务器/自托管渠道，GitHub Release 作为所有平台的事实源。

CLI 的安装方式不改变 Agent runtime；`kevin` 只是调用同一套 `packages/core`、`packages/host` 和 `packages/storage`。每次发布必须验证 `kevin init`、`kevin doctor`、数据库迁移和升级回滚。

## 11. 分阶段实施

先完成完整系统基线，再收敛个人产品形态。基线完成定义和 K01–K18 以 [基线文档](agent-system-baseline.md) 为准；旧 Phase 编号及周数不再作为开发顺序。

### B0：契约、基线映射与技术验证

- 逐项映射现有 TS 和旧 Python 能力：复用、补齐、替代、淘汰或外部待验收。
- 固化 Task/Run/Action/Event、Grant、工具、输入队列和 Goal/Plan/Routine 接口。
- 冻结支持矩阵；验证 SQLite 与服务所有权，保留平台执行隔离接口，形成 ADR。
- 先修默认监听、认证/CORS 和有限循环；明确工具能力与风险。

验收：每项缺口有模块归属和测试入口，关键技术有证据；不要求此时实现恢复 Worker。

### B1：可靠的单次执行

- 解耦 core 与具体 Store/宿主实现，建立使用方 ports。
- 统一模型、上下文、工具参数与结果、审批、预算、等待及停止语义。
- 所有动作通过统一授权入口，验证输出限制和取消能力；真实执行隔离按用户决定独立暂缓。
- 使用现有客户端和 fake provider 验证，同时保留真实环境验收清单。

验收：K02–K06 的单次执行路径通过；错误与权限失败不静默放行。

### B2：持久工作与常驻服务

- SQLite、迁移、JSON importer、短事务与状态版本控制。
- durable Inbox/Queue、Run lease/epoch、Action Ledger、checkpoint、outbox。
- 输入介入、等待释放租约、实际暂停/取消、重试与 unknown 核对。
- 持久预算、统一服务所有权、崩溃重启、时区/DST、漏跑与重叠策略。

验收：K07–K12；包括执行成功未落盘、旧 Worker 恢复、并发重复请求和子进程取消。必须验证真实执行收敛，不能只检查状态字段。

### B3：完整基线与组合验收

- Markdown Memory、内容版本确认、索引修复、产物内容/哈希与来源。
- 多客户端一致性、事件重放/去重/过期游标、诊断脱敏。
- 一致快照与新目录完整恢复；旧备份恢复先冻结调度并核对外部动作。
- 用薄的 personal 应用贯通代码任务、研究报告、周期监测；真实 Provider/MCP 和平台证据单独记录。

验收：冻结范围内 K01–K18 通过；没有证据的能力不得标记完成。

### P1：个人工作策略与产品定义

进入条件：B3 基线通过；B 阶段已验证的 Goal/Plan/Routine 契约继续复用。

- 完善身份、Project、长期目标、版本化计划与完成证据。
- 定义自主延续的授权/预算/停止条件、通知合并和安静时间。
- 决定单 Agent 默认能力，处理 team/collaboration 的产品入口与兼容性。
- 确认 Kevin 命名、配置迁移和最终交互对象。

验收：一个身份可处理多个隔离任务；跨会话继续工作且不会串用审批、账户或项目数据。

### P2：个人产品交互与连接

- 完善交办入口、进行中工作、待处理事项、产物，以及记忆/连接/设置管理。
- Today/Chat/Tasks/Activity 是候选信息架构，依据 P1 场景确定，不反向要求重写内核。
- 完成连接器配置、独立 scope/revoke、设备 Bridge pairing 与短期能力授权。
- Web/Terminal 共用 API 与事件；Desktop 为可选客户端，不复制 runtime。

验收：仅通过产品界面完成交办、介入、审批、查看成果、修复连接和恢复；Bridge 断开和撤销真实生效，远程执行另在 C1 验证。

### P3：完整分发与自托管

- kevin CLI、Bun compile、GitHub Release、自有 Homebrew tap、Docker/Compose。
- 固定运行时版本，逐平台验证安装、初始化、诊断、升级、回滚和数据恢复。
- 迁移品牌/配置前缀，完成文档、截图、CHANGELOG、SECURITY 与发布检查。
- 保留原有完整发布目标，不以基线验收代替新机器和发行包验收。

验收：用户可按文档安装并完成产品闭环；每个发行平台有独立证据。

### C1：Cloud Worker

进入条件：本地基线和产品完成定义通过，明确威胁模型、服务身份、成本、数据区域与事故响应。

- Control Plane、Postgres、Queue、隔离 Worker、对象存储、Secret Manager 和观测。
- 共用 Run/Event 契约，独立验证服务隔离、租约、凭据及远程网络。
- 云端使用本地设备能力必须经过获授权且在线的 Bridge。

验收：关闭客户端后云端工作继续；离线设备能力明确等待；用户隔离、暂停、审批和恢复分别通过。

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

### 12.1 可测量的 v1 门槛

这些数字是验收门槛，不是当前能力声明；如果产品目标改变，要在 ADR 中改动并重新评审：

- 本地 API 健康检查在 1 秒内返回；事件从 worker 写入到 Web 投影的 p95 延迟不超过 2 秒。
- 正常退出或被杀进程后，未完成的本地任务在 60 秒内恢复为可执行或明确的 `reconciling` 状态；结果不确定的 Action 标为 `unknown`。
- 同一写请求的重复 `Idempotency-Key` 不创建第二个 Task/Run；测试至少覆盖并发重复提交。
- 100 个连续 Event 的重放结果与实时投影一致；重复事件不会重复显示或重复写入副作用。
- `kevin export` → 删除 → `kevin import` 后，Task、Run、Event、Markdown 正文与所选 Artifact 内容/哈希可恢复，凭据不会被导出；用于完整恢复的备份不得遗漏受恢复任务引用的文件；旧快照恢复先冻结调度并核对外部动作。
- 关闭网络、无 API key、模型超时、工具超时、磁盘只读和数据库锁定都能得到可解释错误，不出现静默成功。
- Prompt injection、路径穿越、私网 SSRF、未授权 Connector、过期 approval token 各至少有一条失败测试。

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

第一批按 [基线文档第 10 节](agent-system-baseline.md#10-交付关口与首批任务) 执行：能力映射与证据登记 → 版本化契约 → 安全默认值 → SQLite/常驻服务 spike 与隔离接口预留 → core ports 解耦 → 三类场景的薄验证入口。

命名迁移、最终页面设计和云端实现分别进入 P/C 阶段。不能只先建业务表而遗漏 Action Ledger、授权、输入队列和恢复契约，也不能在 Worker 尚未实现时宣称已经通过租约恢复验收。

## 17. 实施治理与变更控制

### 17.1 每个阶段的交付证据

每个 B/P/C 阶段必须产出四类证据：

1. 代码：实现、migration、配置和测试。
2. 文档：架构决策、运行说明、用户可见行为和已知限制。
3. 演示：一条从输入到产物的可重复脚本或录屏。
4. 验收：命令、环境、版本、结果和未通过项；不能只写“已测试”。

### 17.2 ADR 必须记录的未决选择

- SQLite 驱动和 Bun 版本兼容性。
- CLI 主渠道已选独立 binary + GitHub Release/Homebrew；fallback package 的运行时依赖和平台兼容性需验证。
- 本地凭据进入 SQLite，但只保存加密密文；数据库加密密钥的保护方式（系统 keychain 或受控环境变量）需要在 ADR 中确定。
- Cloud Worker 的容器/VM、队列、对象存储和 Postgres 供应商。
- 事件 schema 的兼容策略和保留时间。
- Markdown Memory 的目录、文件命名、引用格式和 SQLite 元数据索引规则。

未决选择在实施前必须有 spike 结果；方案中的占位名不能直接变成生产依赖。

### 17.3 发布和回滚策略

- 数据库 migration 只允许向前兼容；破坏性变更采用 expand → migrate → contract。
- 新 Scheduler、Policy 和 UI 行为使用 feature flag 灰度，不在一个提交里同时开启所有路径。
- 每次发布保留上一版本启动方式、数据库备份和配置快照。
- 回滚前检查新版本是否已经写入不可逆 schema 或外部副作用；不能把“代码回滚”误当作“数据和外部系统回滚”。
- 重大行为变化在 CHANGELOG 中标明默认策略、迁移动作和用户需要重新授权的连接器。

## 18. 完成定义

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
- 用户可以删除自己的 Conversation、Task、Memory 和 Artifact，并能验证凭据没有进入导出包。
- 默认本地部署不会把 Host 暴露到局域网或公网；远程部署必须明确开启认证和网络策略。
- Prompt injection、SSRF、路径穿越、重复副作用和过期审批均有自动化失败测试。
- 仓库以 Kevin 名称公开分发，文档、脚本、截图和实际行为一致。

达到这个定义后，Kevin 才从“Agent runtime 工程”变成一个真正可使用、可展示、可继续云化的个人 Agent 产品。
