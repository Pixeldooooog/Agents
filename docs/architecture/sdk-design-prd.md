# PRD：Kevin SDK 目录与公共接口设计

> 状态：设计提案，未实施。日期：2026-10-26。
> 关联：[内核边界](kernel-boundaries.md)、[Agent 系统基线](../agent-system-baseline.md)、[模块地图](../module-map.md)。

## 1. 背景与问题

`packages/core/src/sdk/` 目前有 86 个文件、约 12,500 行，约占 core 源码的三分之一；对应测试约 8,100 行，占全部测试的 74%。但 host、Web、Terminal 和 core 的其他模块**都没有引用它**。

主要问题：

| 问题 | 现状 | 影响 |
|---|---|---|
| 位置错误 | SDK 放在 `core` 内部，并通过 `@kevin/core/sdk` 导出 | 内核与对外接口耦合；core 依赖面和体积被 SDK 拉大 |
| 职责混杂 | 同一目录里有客户端 API、会话存储、文件历史回滚、上下文统计、MCP elicitation、权限模式、wire 校验、远程 worker 传输 | 领域逻辑落在“SDK”名下，真正的所有者（session、workspace、mcp、permissions）反而缺失 |
| 复刻无关协议 | CCR 远程 worker、批量上传、混合传输、WebSocket 代理/TLS 等约 2,600 行 | 这是编码 CLI 的远程运行协议，不是个人智能体的对外 SDK；当前没有消费者 |
| 公共面失控 | `index.ts` 用 `export *` 导出 60+ 个文件；`sdkPublicAliases.ts` 再给同一批符号起 `SDK*` 大写别名 | 无法判断哪些是稳定 API；任何内部重命名都是破坏性变更 |
| 运行模式单一 | 只能进程内调用 `AgentRunService` | 不能作为远程客户端连接常驻 host，与基线“客户端连接同一服务”的目标冲突 |

## 2. 目标与非目标

### 目标

1. SDK 作为**独立 package** `@kevin/sdk`，是第三方和 Kevin 自有客户端访问智能体的**唯一受支持入口**。
2. 同一套公共 API 支持两种运行模式：**远程**（连接常驻 host，默认）和**嵌入**（进程内运行，用于测试、脚本和单机集成）。
3. 公共面小且显式：每个导出都有归属和稳定级别，内部模块不可从包外导入。
4. 公共事件与 wire 协议有版本号，校验发生在边界，外部数据一律按 `unknown` 处理。
5. SDK 不承担领域逻辑：会话存储、文件历史、上下文、权限、MCP 都由 core 中对应模块负责，SDK 只做投影和转发。

### 非目标

- 不实现 CCR 远程 worker、批量事件上传、WebSocket 代理。若未来需要云端 worker，按 C1 阶段另起 package。
- 不提供浏览器专用 bundle。Web 应用暂时继续使用自己的 `apiClient`，等 SDK 远程模式稳定后再迁移。
- 不兼容旧的 `SDK*` 别名和 `@kevin/core/sdk` 导入路径。项目尚未发布，按 AGENTS.md 规则不保留兼容层。

## 3. 用户与场景

| 用户 | 场景 | 运行模式 |
|---|---|---|
| Kevin Terminal / Web | 发起任务、接收流式事件、审批、取消、查看会话 | 远程 |
| 开发者脚本 | 写一个定时脚本让 Kevin 汇总资料并返回结构化结果 | 远程或嵌入 |
| 第三方集成 | 在自己的应用里嵌入 Kevin，提供自定义工具和审批 UI | 远程 |
| 内核测试 | 用假模型、假传输做确定性契约测试 | 嵌入 + `testing` |

## 4. 设计原则

1. **依赖方向**：`apps → @kevin/sdk → @kevin/core/contracts`。只有 `@kevin/sdk/embedded` 子路径允许依赖 core 运行时。core 永远不导入 sdk。
2. **传输与 API 分离**：公共 API 只依赖 `Transport` 接口；HTTP/SSE、stdio JSONL、进程内都是可替换的实现。
3. **一个概念一个名字**：类型统一用 `Kevin` 或领域名前缀（`KevinClient`、`Session`、`Run`、`RunEvent`），不再出现 `Sdk` / `SDK` 双套命名。
4. **公共面显式列出**：`src/index.ts` 只逐个具名导出；禁止 `export *`。
5. **错误可区分**：配置错误、传输错误、协议错误、服务端拒绝、超时、用户取消分别用不同错误码，不吞成通用 `Error`。
6. **资源有归属**：每个流都有明确的关闭路径；`AbortSignal` 贯穿所有 I/O；`for await` 提前退出时释放读取器和监听器。

## 5. 目标目录结构

```text
packages/sdk/
├── package.json             # exports: ".", "./embedded", "./transports/stdio", "./testing"
├── tsconfig.json
├── src/
│   ├── index.ts             # 公共面：逐个具名导出，唯一入口
│   │
│   ├── client/              # 入口对象与配置
│   │   ├── kevinClient.ts       # createKevinClient() → KevinClient
│   │   └── clientOptions.ts     # 选项类型与边界校验
│   │
│   ├── sessions/            # 会话句柄与查询（数据由服务端/core 拥有）
│   │   ├── session.ts           # Session：send / resume / close
│   │   └── sessionQueries.ts    # list / get / messages / fork / rename
│   │
│   ├── runs/                # 一次运行的流与控制
│   │   ├── runHandle.ts         # Run：events（AsyncIterable）+ result（Promise）
│   │   ├── runControl.ts        # approve / deny / interrupt / cancel / sendInput
│   │   └── runResult.ts         # 终态结果类型与从事件归约
│   │
│   ├── events/              # 公共事件模型（版本化）
│   │   ├── runEventTypes.ts     # RunEvent 判别联合，schema_version: 1
│   │   └── runEventGuards.ts    # 类型守卫与窄化
│   │
│   ├── tools/               # 客户端自定义工具
│   │   ├── defineTool.ts        # defineTool({ name, schema, handler, risk })
│   │   └── clientToolBridge.ts  # 调用请求 → 本地 handler → 结果回传
│   │
│   ├── approvals/           # 审批回调契约
│   │   └── approvalHandler.ts   # onApproval(request) → decision
│   │
│   ├── transports/          # 传输实现（API 只依赖接口）
│   │   ├── transport.ts         # Transport 接口
│   │   ├── httpTransport.ts     # REST + SSE，连接常驻 host（默认）
│   │   └── stdioTransport.ts    # 子进程 JSONL（子路径导出）
│   │
│   ├── wire/                # 线协议：编码、分帧、校验
│   │   ├── wireSchema.ts        # v1 消息 JSON Schema
│   │   ├── wireValidation.ts    # unknown → 已验证消息
│   │   ├── jsonlFraming.ts      # JSONL 分帧
│   │   └── sseFraming.ts        # SSE 分帧（可复用 core/models 的实现）
│   │
│   ├── errors/
│   │   └── kevinSdkError.ts     # KevinSdkError + code 枚举
│   │
│   ├── embedded/            # 进程内模式，唯一允许依赖 core 运行时
│   │   ├── embeddedTransport.ts # 包装 AgentRunService，实现 Transport
│   │   └── runEventProjection.ts# core RuntimeEvent → 公共 RunEvent
│   │
│   └── testing/             # 公开的测试工具
│       ├── fakeTransport.ts     # 脚本化事件序列
│       └── recordedRuns.ts      # 录制/回放 wire 记录
│
└── test/
    ├── contract/            # 公共 API 契约：事件顺序、审批、取消、错误码
    ├── transports/          # 本地 HTTP fixture server、stdio 子进程
    ├── wire/                # 分帧、损坏输入、超限、版本不匹配
    └── fixtures/            # 录制的 wire 记录（golden files）
```

**命名约定**：目录是稳定的领域名（`sessions`、`runs`、`transports`）；文件名是该领域内的具体职责（`runControl.ts`、`httpTransport.ts`）。文件名不加 `sdk` 前缀，因为 package 名已经表达了这一点。

### package.json 导出

```json
{
  "name": "@kevin/sdk",
  "exports": {
    ".": "./src/index.ts",
    "./embedded": "./src/embedded/index.ts",
    "./transports/stdio": "./src/transports/stdioTransport.ts",
    "./testing": "./src/testing/index.ts"
  },
  "dependencies": { "@kevin/core": "workspace:*" }
}
```

根入口只用到 `@kevin/core/contracts` 的类型；只有导入 `@kevin/sdk/embedded` 时才会加载 core 运行时。远程模式的使用者因此不需要带上 runtime、工具和存储。

## 6. 公共 API

### 6.1 使用示例

```ts
import { createKevinClient, httpTransport } from "@kevin/sdk";

const kevin = createKevinClient({
  transport: httpTransport({ baseUrl: "http://127.0.0.1:8787", token: process.env.KEVIN_TOKEN })
});

const session = await kevin.sessions.create({ title: "周报" });
const run = session.send("汇总本周 docs/ 下的改动", { signal });

for await (const event of run.events) {
  if (event.type === "message.delta") process.stdout.write(event.delta);
  if (event.type === "approval.requested") await run.approve(event.approvalId);
}

const result = await run.result; // { status, content, usage, ... }
```

嵌入模式只替换传输，其余代码不变：

```ts
import { embeddedTransport } from "@kevin/sdk/embedded";
const kevin = createKevinClient({ transport: await embeddedTransport({ repoRoot }) });
```

### 6.2 核心对象

| 对象 | 职责 | 主要成员 |
|---|---|---|
| `KevinClient` | 入口，持有传输和配置 | `sessions`、`runs.get(runId)`、`close()` |
| `Session` | 一段持续对话 | `send()`、`messages()`、`fork()`、`rename()` |
| `Run` | 一次运行 | `events`、`result`、`approve()`、`deny()`、`interrupt()`、`cancel()`、`sendInput()` |
| `RunEvent` | 公共事件判别联合 | 见 6.3 |
| `Transport` | 传输接口 | `startRun()`、`control()`、`subscribe()`、`query()`、`close()` |

`run.events` 只能被消费一次；`run.result` 可在不消费事件的情况下等待终态（内部自行排空）。

### 6.3 公共事件（schema v1）

| 事件 | 含义 |
|---|---|
| `run.started` | 运行开始，携带 `runId`、`sessionId` |
| `message.delta` | 文本增量，暂态，不保证可重放 |
| `message.completed` | 已校验的完整模型消息 |
| `tool.started` / `tool.completed` | 工具调用开始与结果（含 `isError`） |
| `approval.requested` | 需要审批，携带 `approvalId`、工具名、参数摘要 |
| `input.requested` | 智能体请求用户补充输入 |
| `run.completed` | 终态：`finished` / `awaiting_approval` / `error` / `canceled` |

所有事件都带 `event_id`、`schema_version`、`occurred_at`、`run_id` 和 run 内单调递增的 `sequence`，与基线文档第 8 节的事件契约保持一致。core 内部 `RuntimeEvent` 的字段变化只影响投影层，不影响公共事件。

### 6.4 Transport 接口

```ts
export interface Transport {
  startRun(request: StartRunRequest, signal?: AbortSignal): Promise<RunSubscription>;
  control(runId: string, command: RunControlCommand, signal?: AbortSignal): Promise<void>;
  query<K extends QueryKind>(kind: K, params: QueryParams[K], signal?: AbortSignal): Promise<QueryResult[K]>;
  close(): Promise<void>;
}

export interface RunSubscription extends AsyncIterable<RunEvent> {
  readonly runId: string;
  close(): Promise<void>;
}
```

`RunControlCommand` 覆盖 `approve`、`deny`、`interrupt`、`cancel`、`input`。审批命令必须回传事件里收到的 `approvalId`，与现有 HTTP 审批接口一致。

### 6.5 错误码

`KevinSdkError.code` 的取值：`invalid_options`、`transport_unavailable`、`protocol_error`、`unsupported_schema_version`、`unauthorized`、`not_found`、`conflict`、`timeout`、`canceled`、`server_error`。HTTP 状态码映射集中在 `httpTransport.ts`。

## 7. 现有 `core/src/sdk` 的迁移去向

| 现有内容（约行数） | 去向 | 理由 |
|---|---|---|
| `agentSdkClient`、`sdkFacade`、`sdkSession`、`sdkQueryOptions`、`sdkTypes`（~1,100） | 重写为 `sdk/client`、`sdk/sessions`、`sdk/runs` | 保留能力，按新 API 收窄 |
| 消息与事件投影 `sdkMessages`、`sdkEvent*`、`sdk*Messages`（~1,800） | `sdk/events` + `sdk/embedded/runEventProjection` | 公共事件模型重新定义；投影只保留嵌入模式需要的部分 |
| wire 校验、JSON Schema、JSONL/SSE 分帧、`sdkStructuredIo`（~2,300） | `sdk/wire` | 与 core/models 的 SSE 分帧去重 |
| 控制处理、活动 turn、异步消息队列、`sdkProtocolRunner`（~2,000） | 控制契约放到 `sdk/runs/runControl`；**输入队列与中断语义下沉到 core 执行层** | 基线 K10 要求输入队列是持久事实，归执行层所有 |
| 本地 JSONL 传输（~270） | `sdk/transports/stdioTransport` | 保留子进程模式 |
| 会话记录、fork/rename/tag、压缩（~690） | `core/session` | 会话数据属于领域层；SDK 只调用 |
| 文件历史、回滚、读状态（~1,350） | `core/workspace/fileHistory` | 文件快照是工具与工作区的职责 |
| 上下文用量（~200） | `core/context` | 上下文预算是 runtime 的职责 |
| MCP elicitation 与控制记录、权限模式 | `core/mcp`、`core/permissions` | 回到能力的所有者 |
| CCR 客户端、混合/SSE worker 传输、批量上传、WebSocket 连接/代理/TLS、传输 URL（~2,600） | **删除** | 编码 CLI 的远程 worker 协议，无消费者；C1 需要时另行设计 |
| `sdkPublicAliases`（~190） | **删除** | 重复命名 |
| `sdkFileHistoryMigration` | **删除** | 迁移来源不属于本项目 |

预计迁移后 SDK 包约 3,000–4,000 行；约 2,000 行领域逻辑回到 core 的正确位置；约 2,800 行删除。

## 8. 分阶段实施

| 阶段 | 内容 | 完成标准 |
|---|---|---|
| S0 冻结 | 停止向 `core/src/sdk` 添加功能；为第 7 节每一行建 issue 或清单项 | 迁移清单无未归属项 |
| S1 领域下沉 | 会话、文件历史、上下文用量、MCP elicitation、权限模式迁入 core 对应模块，测试随迁 | core 测试全绿；`core/src/sdk` 不再包含领域逻辑 |
| S2 新包骨架 | 建 `packages/sdk`：`client`、`runs`、`events`、`errors`、`transports/transport.ts`、`embedded` | 嵌入模式跑通“发起 → 流式 → 审批 → 完成/取消”契约测试 |
| S3 远程模式 | `httpTransport` 对接 host 的 REST + SSE；host 补齐版本化事件流与断线重连游标 | 本地 HTTP fixture 与真实 host 两套测试通过 |
| S4 切换与删除 | Terminal 改用 SDK；删除 `core/src/sdk` 与 `@kevin/core/sdk` 导出；更新模块地图 | 仓库中无 `core/sdk` 引用；`bun run check` 通过 |
| S5 自定义工具 | `defineTool` + 客户端工具桥，经过与内置工具相同的权限与审批入口 | 客户端工具被拒绝、超时、取消均有测试 |

每阶段单独提交，使用 emoji commit。S1 与 S2 可以并行；S3 依赖 host 事件流。

## 9. 验收标准

1. `@kevin/sdk` 根入口不会传递加载 core 运行时（通过检查依赖图验证）。
2. 公共导出清单不超过约 40 个符号，并且每个都有文档注释。
3. 同一份契约测试分别在嵌入传输和 HTTP 传输上运行，结果一致。
4. 失败路径都有测试：损坏帧、未知 `schema_version`、断线重连、重复审批（409）、中途取消、`for await` 提前退出后资源被释放。
5. core 中没有任何文件导入 sdk；sdk 只通过 `@kevin/core/contracts`（根入口）或 `@kevin/core`（embedded）访问内核。
6. 文档：模块地图更新，公共 API 示例可直接运行。

## 10. 待决问题

1. 嵌入模式是否继续允许与常驻 host 共用状态目录？基线文档要求隔离，建议嵌入模式强制使用独立状态目录。
2. 公共事件是否直接采用 `contracts/` 中的 Event v1 类型？建议采用，以免出现第三套事件模型；前提是 runtime 先切换到 contracts。
3. Web 何时从自有 `apiClient` 切换到 SDK？建议在 S3 稳定后进行，并评估浏览器端 bundle 体积。
