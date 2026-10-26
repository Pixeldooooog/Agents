# Kevin 智能体内核：边界与实施顺序

本文件描述完整目标分层与当前差距，不把规划当成已完成能力。工程规则见仓库 `AGENTS.md`。本轮从协议入口的正确性开始，不重写 UI，不实现暂缓的原生沙箱。

## 依赖方向

```text
apps (Web / Terminal)
  → host (API / auth / configuration / composition)
    → runtime (turn loop / permissions / approval / cancellation)
      → models (normalized model turn ← protocol adapters ← HTTP)
      → tools (schema validation → permitted handler execution)
        → built-in tools / skill instructions / MCP capabilities

hooks → documented runtime lifecycle decisions, never a second executor
storage/execution ports ← host-selected implementations
```

上图是职责关系；模型返回工具调用提议，只有 runtime 可以决定是否执行。Skill、MCP 和 Hook 不组成逐级包裹模型的“继承层级”，它们是接入不同边界的能力。

## 每层负责什么

| 层 | 输入 → 输出 | 所有权 | 禁止承担 |
| --- | --- | --- | --- |
| 模型协议 | 内部消息、工具定义 → 文本、工具调用、usage | Chat / Messages / Responses 编解码及能力限制 | 工具执行、文件发现、审批、运行状态写入 |
| 模型传输 | URL/请求体/取消信号 → 外部未知数据 | HTTP、超时、响应读取、SSE 分帧与资源释放 | 解释 Skill 或修改工具权限 |
| Runtime | 用户任务、已验证模型结果 → 事件与任务结果 | 多轮顺序、预算、工具结果配对、审批与取消 | 直接解析供应商私有 JSON |
| Tool | 受控上下文、已验证参数 → ToolResult | 注册、schema、执行、错误结果、资源限额 | 自己发起绕过 runtime 的模型循环 |
| Skill | 目录与元数据 → 按需读取的指令和资源 | SKILL.md 发现、解析、作用域与来源 | 通过文档内容授予权限或执行命令 |
| MCP | 外部协议消息 → 内部 tool/resource/prompt | 发现、连接、取消、分页、命名与错误转换 | 绕过审批、污染模型消息类型 |
| Hook | 明确的生命周期输入 → 限定决策或观察结果 | 时机、顺序、超时、失败策略、审计 | 任意状态写入、隐式执行工具或提升权限 |
| Host / Persistence | 配置和存储端口 → 可运行的实例 | 鉴权、密钥来源、装配、持久化适配器 | 在路由中实现 agent loop |

## 现状审计与首批改动

### Models

现有实现位于 `packages/core/src/models/`，已有三种主协议的工具编码/解码及 usage 归一化。Gemini 目前只有文本完成。运行时非流模式调用 `completeModelTurn`；开启 `stream` 时，三种主协议通过 `streamModelTurn` 接收原生增量并校验完整工具回合。

首批已实现：

- 已支持的协议别名归一化；未知值明确抛出 `ModelConfigError`，不再落到 Chat 默认分支。
- 主协议的工具调用必须包含非空名称、真实关联 ID、合法对象参数；不再把损坏 JSON、数组、缺失 ID 变成 `{}` 或合成 ID。
- Responses 严格使用 `call_id`，不把输出项 `id` 当作工具结果关联键。
- 单轮重复工具 ID 被拒绝，使用 Set 在线性时间内检查。
- 外部 HTTP 结果为 `unknown`；成功响应 JSON 损坏与 HTTP 非成功状态分别报告 `ModelProtocolError`、`ModelHttpError`。HTTP 错误保留状态码。
- 缺失必要响应结构和已知截断/未完成状态不再作为成功空回答。未宣称覆盖协议全部字段或内容类型。
- Gemini 收到工具定义或工具历史时明确报告未支持，不再静默忽略。
- 模型 payload 解析不再依赖 HTTP 模块；SSE 读取器在异常和消费结束时释放。使用项目要求的 Bun 1.4.4 原生 AbortSignal.any，取消旧的无清理回退监听器。

P1 已实现：

- `streamModelTurn` 提供统一 `text_delta`、`tool_call_delta`、`usage`、`completed` 契约。增量是暂态；整个回合通过终态及参数校验后才返回 `ModelTurn`。回调被顺序 await，异常与取消直接终止消费。
- 独立 SSE 分帧器支持 CR/LF/CRLF、多行 data、注释与分片 UTF-8；未完成帧、无效编码明确失败。单事件上限 1 Mi UTF-16 code units，整轮数据上限 16 Mi code units / 65,536 个事件，条目索引限制为 0–1023。读取器在结束或异常时释放。
- Chat 按 index 组装交错工具参数，验证 ID/名称不可改变、索引连续、参数合法、关联 ID 唯一，以及 finish reason 与工具结果一致；必须收到 `[DONE]`。
- Responses 校验 item_id/output_index，核对增量参数与最终 item、最终 response.output 的一致性；要求 completed 终态。保留 reasoning、message、function_call 的原始顺序，并请求 encrypted reasoning，使用 `store: false` 的手动历史回放。
- Messages 校验块顺序、参数 JSON、stop reason 与工具调用一致性；合并起始/结束 usage，保留 thinking signature 和 redacted thinking。内部推理不作为面向用户的文本增量发出。
- 原生上下文随 assistant Message 保存，由 runtime 透传；只有 protocol/model/baseUrl 都匹配时回放。切换目标时使用归一化文本/工具历史，不能假设跨模型保留原推理状态。API key 不进入原生上下文。
- `streamText` 复用完整回合解析器并拒绝工具输出，删除旧的独立文本状态机。Gemini 仍无原生流式工具支持。
- Runtime 在模型回合完整校验后走原有工具权限、审批和执行路径。文本增量即时传给客户端，但不逐 token 写入 JSON store；持久事件使用已验证的 `model_message`。失败/取消前的增量不会被当作完整消息保存。

验收范围仍是本地协议 fixture 和真实本地文件工具，不包含供应商线上兼容性。Responses 内置服务工具、音频等额外输出类型未实现；本批不宣称所有 provider 扩展已覆盖。

### Tools / Runtime

已有 `toolRegistry`、schema 校验、`runtimeToolPermissions` 和审批恢复。接下来先验证并修复**一次模型返回多个工具调用、其中一个暂停审批**时的剩余调用和结果配对；当前 PendingApproval 只记录单个当前工具，不能直接宣称多调用恢复完整。

统一模型工具与外部工具的执行入口；明确并发/顺序策略、超时、取消、输出上限与错误契约。工具业务行为继续留在专属模块，注册只装配，不为每个工具创建没有用途的类。

### Skills

已有 `extensions/` 下 SKILL.md 发现/解析/安装与按需读取，`runtimeMessages` 注入元数据。下一步审计 `skill.use`、allowed-tools 和启用逻辑与用户权限的关系，区分“允许向模型展示”与“允许执行”。明确资源路径、输入替换、动态上下文和撤销语义。

### MCP

已有 provider 注入与 resource/prompt 调用、服务器记录和管理工具。还需对真实 transport 的连接、initialize、tools/list、tools/call、分页、取消、关闭做独立验收；不能把注入 provider 的测试视为生产连接通过。外部工具必须统一映射到工具注册和权限边界，资源和 prompt 不伪装成工具结果。

### Hooks

现有 `hooks/` 定义事件、动作、记录和工具，主运行循环未见对这些生命周期事件的实际调度。下一阶段先定义受限、可测试的事件契约，再接入；尤其 `run_command` 不能只因记录存在就自动执行。预执行阻止可以收紧权限，不能放宽权限；观察型 hook 失败与控制型 hook 失败需要不同的明确策略。

## 验收顺序

1. **P0 协议输入输出边界（本批）**：配置校验、协议错误、参数解析、关联 ID、未支持能力显式拒绝；保留现有合法请求回归测试。
2. **P1 流式模型回合**：分帧/多字节/中断/错误/终态、原生字段回放；真实供应商验证按 provider + model + endpoint 单独记录。
3. **P2 统一工具回合**：多调用、审批恢复、拒绝、取消、预算、重复结果；真实文件工具完整链路。
4. **P3 Skill 边界**：发现与加载、范围、资源访问、权限不可扩张。
5. **P4 MCP 接入**：transport/session 与外部能力映射、真实本地 fixture server、取消与重连。
6. **P5 Hook 接入**：限定生命周期、确定性顺序、失败策略、不会绕过工具权限。
7. **P6 Host / App 验收**：UI 状态只来自真实运行事件；一条任务从交办到结果，中间可审批、取消、失败与恢复。

这个顺序不缩减目标架构，也不代表每个阶段都要增加新的 package。先在现有清晰目录内收敛契约；只在依赖隔离确有需要时拆包。

## 证据标准

本地 fixture 测试验证适配与失败路径；本地 HTTP server 验证传输；真实模型验收另记端点与模型。测试通过不自动证明线上支持、后台持续运行或完整恢复。每个批次用 emoji commit，并记录实际测试数量和剩余缺口。

## P0 验证记录

- Bun 1.4.4：最终 `bun test packages` **212 pass / 0 fail**，其中新增协议边界测试 11 个。
- `bun run check` 的 core/host/terminal TypeScript、Web production build、终端 file-index/render/interaction/app smoke 全部通过；随后仅调整新增测试的隔离方式并重新跑上述 212 项测试。
- 新增 HTTP 与流消费测试使用独立本地 server；不替换全局 fetch，避免影响其他测试。
- 本批没有使用真实模型服务；不宣称 provider/model 线上验收或完整流式工具支持。

## P1 文本流基础验证记录

- Bun 1.4.4：`bun run check` 通过，**234 pass / 0 fail**；新增 22 项 SSE/文本流测试。
- 覆盖逐字节 UTF-8、CR/LF/CRLF、多行事件、事件上限、截断、消费端提前退出、协议终态、错误响应、Messages 请求参数、取消和等待响应体超时。
- core/host/terminal 类型检查、Web production build、终端四项 smoke 均通过。最终将文本流 step 类型移入共享 contracts 后，另跑 core 类型检查通过。
- HTTP 测试使用本地 fixture server；无真实供应商验收，流式工具回合与原生上下文回放仍未完成。

## P1 工具流与上下文回放验证记录

- `bun run check`：**256 pass / 0 fail**，core/host/terminal 类型检查、Web production build 与终端四项 smoke 全部通过。
- 新增 22 项测试：交错调用、身份冲突、损坏参数、终态不一致、原生上下文隔离、异步消费/取消，以及三协议 HTTP fixture。
- Runtime 使用真实本地文件工具验证：完整回合后执行；中途断流、后续调用损坏、取消时零执行；审批前不写文件。
- Responses 测试在审批暂停后重新打开 JSON store，验证 reasoning/call_id 保留并在恢复请求中按原顺序回放。该证据仅覆盖已有审批恢复路径，不代表任意崩溃恢复或持久任务执行已完成。
- 更新原有 SDK 流模式 fixture 为真正 SSE，并断言新增流事件。文本增量实时交付但不逐 token 持久化。
- 下一批为 P2：一次模型返回多个工具调用时，审批暂停/恢复不能丢失后续调用，并保留工具循环预算与 usage。
