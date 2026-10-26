# CC 风格历史实现与 nxs 内核参考评估

日期：2026-10-26。状态：评估记录，未据此实施新功能。

> 来源更正：用户确认 `nexus-code` 是此前自行迁移、补全的 CC 风格实现，不能当作官方 CC 源码或成熟行为的权威依据。下文“CC”仅指这份历史参考，所有采用建议均需独立验证。完整复审见 [nexus-code 整体审查](nexus-code-review.md)。

## 目的与证据范围

记录 Kevin 内核可以从 CC 和 nxs 借鉴的设计，供当前代码结构清理完成后决策。本文件不替代现有 [内核边界](kernel-boundaries.md) 和 [验收记录](kernel-acceptance.md)，不扩展当前 P0–P6 范围，也不启动暂缓的原生沙箱工作。

本次是静态源码评估，没有编译或运行参考项目，也没有进行真实模型、跨平台或持久恢复验收。

| 对象 | 检查位置与基线 | 限制 |
| --- | --- | --- |
| Kevin | 本仓库；初次检查 HEAD `082b173`，落文时 HEAD `00425d2` | 正在并行清理代码，存在未提交变更；下列问题是检查时快照，实施前需重新确认 |
| CC | `../../../nexus-code/src-origin`（Kevin 仓库外的同级本地目录，不纳入版本控制） | 本地部分源码，未核实对应官方版本；部分条件编译引用缺失，不能当成完整可运行发行版 |
| nxs | `/Users/berhand/program/Work/Nexus/nexus-agent-sdk-go`，HEAD `55dc92f1` | 指该仓库的 `cmd/nxs` 进程运行时及其 SDK 内核；不是泛指整个 Nexus 产品 |

历史实现来源链接指向工作区同级参考仓库，不保证在 Kevin 的 GitHub 页面可访问。nxs 下文路径相对上述外部仓库，仅作为阅读索引，不构成 Kevin 的运行依赖。

## 总体判断

**nexus-code 提供行为设计候选和历史实现经验，但补全代码中存在占位与契约不匹配；nxs 提供模块拆分参考。两者都需要独立验收，Kevin 不应把任一实现当成正确性标准。**

参考顺序是：提取可观察行为 → 确定状态与资源的唯一归属 → 定义契约和失败语义 → 对照 Kevin 已有实现 → 补上必要部分。不要为了“对齐”复制目录、恢复废弃 SDK，或创建没有调用方的抽象。

## 历史 CC 风格快照：行为契约候选

| 领域 | 源码观察 | Kevin 适合吸收的内容 |
| --- | --- | --- |
| 会话连续性 | [QueryEngine.ts](../../../nexus-code/src-origin/QueryEngine.ts) 将用户输入追加到 mutableMessages，并在模型请求前保存 transcript | 区分 session 历史、一次 run、一次模型请求；定义输入何时被接受和保存，以及后续请求如何带入历史 |
| 上下文预算 | [query.ts](../../../nexus-code/src-origin/query.ts)、[microCompact.ts](../../../nexus-code/src-origin/services/compact/microCompact.ts)、[autoCompact.ts](../../../nexus-code/src-origin/services/compact/autoCompact.ts) 协调工具结果预算、裁剪和压缩；自动压缩有连续失败保护 | 保留完整工具调用/结果关联；预算作用于请求投影；压缩失败不能无限循环；摘要和压缩边界需要可追溯 |
| 工具契约 | [Tool.ts](../../../nexus-code/src-origin/Tool.ts) 包含输入验证、依赖输入的并发安全判断、只读/破坏性声明、中断策略和结果上限 | 工具能否并发应由已验证输入及资源影响决定；结果必须有预算；取消语义应显式表达 |
| 执行调度 | [StreamingToolExecutor.ts](../../../nexus-code/src-origin/services/tools/StreamingToolExecutor.ts) 区分可并发与独占工具，并管理顺序和子取消控制 | 参考调度约束与结果对应关系；先保证正确顺序、取消传播和有界并发，再讨论优化 |
| 权限判定 | [permissions.ts](../../../nexus-code/src-origin/utils/permissions/permissions.ts) 结合规则和工具自己的权限检查 | 同一份输入、资源范围与策略应得到同一个结构化决定，解释接口与真实执行共享权威判定 |
| 恢复与终止 | [query.ts](../../../nexus-code/src-origin/query.ts)、[stopHooks.ts](../../../nexus-code/src-origin/query/stopHooks.ts) 区分上下文、输出长度、停止 Hook 等路径 | 区分重试、压缩后重试、续写、终止和用户取消；每条恢复路径有次数/预算上限 |
| 文件修改保护 | [FileEditTool.ts](../../../nexus-code/src-origin/tools/FileEditTool/FileEditTool.ts) 核对读取状态、时间及内容 | 对照 Kevin 已有 read-before-write 能力补充边界测试，不把已有能力误判为缺失 |

### Kevin 检查时发现的具体风险

1. **压缩和回退的单位过细。** [sessionContextToolHandlers.ts](../../packages/core/src/session/sessionContextToolHandlers.ts) 的压缩保留最后两条非 system 消息，回退按单条消息删除。这不能保证 assistant tool call 与其结果成组保留，存在孤立结果的风险。应先定义合法消息组和可回退边界，再修改算法。
2. **权限解释与执行可能不一致。** [permissionDecisions.ts](../../packages/core/src/permissions/permissionDecisions.ts) 在默认允许模式下给出 allow，而 [runtimeToolPermissions.ts](../../packages/core/src/runtime/runtimeToolPermissions.ts) 对外部 MCP 工具及 `hook.add` / `hook.delete` 另行要求批准。应合并判定来源，保留现有更严格的执行约束，不能以统一为名降低权限要求。
3. **普通新 Run 的消息初始化不等于会话恢复。** [runtimeMessages.ts](../../packages/core/src/runtime/runtimeMessages.ts) 的 `runtimeStartMessages` 返回 system 和当前 user 消息。需要沿实际入口确认何处拼接历史；界面能显示历史，不足以证明模型请求带上了历史。这不是“整个仓库完全没有历史功能”的结论。

上述记录不表示清理后的代码仍有同样问题；实施时应重新沿调用链确认并写行为测试。

### 不直接采用的 CC 做法

- `Tool.ts` 同时包含 React 渲染能力；Kevin 内核不能依赖 UI。
- [SkillTool.ts](../../../nexus-code/src-origin/tools/SkillTool/SkillTool.ts) 会将 Skill 的 allowedTools 加入权限规则；Kevin 保持“加载 Skill 不授予工具权限”。[loadSkillsDir.ts](../../../nexus-code/src-origin/skills/loadSkillsDir.ts) 的本地动态 shell 展开也不能成为旁路执行入口。
- 不因 CC 有流式工具执行，就在模型完整 turn 校验之前执行副作用工具；如未来需要，应独立设计并证明安全边界。
- 不复制 IDE、OAuth、团队、遥测、实验开关或整个目录树。
- `query.ts` 引用的 `services/compact/reactiveCompact.ts` 在该快照缺失；不能根据导入语句宣称已读到或验证其完整实现。

## nxs：优先借鉴工程边界

主要结构参考 `docs/architecture.md`，并核对了下列具体实现。目录是责任分配的例子，不是 Kevin 必须照搬的包结构。

| 能力 | nxs 参考位置 | Kevin 的取舍 |
| --- | --- | --- |
| 装配与执行分离 | `internal/agent/runtime/runtime.go` 的 `installConversationAndQuery` 装配 context、query、恢复状态和工具；`internal/agent/query/loop` 承担执行循环 | 优先采用：入口只装配；turn loop 负责顺序和状态转换；具体恢复、工具与上下文行为各有归属 |
| 历史与上下文分离 | `internal/agent/context/runtime.go` 管理运行上下文；`internal/session/transcript.go` 管理 transcript；runtime 负责恢复接线 | 优先采用：持久历史是事实记录，context 是本轮投影；裁剪不能隐式破坏事实记录；不要维护两套竞争的会话事实源 |
| 协议与错误归一化 | `internal/provider` 分离中立请求与协议适配；`internal/provider/context_overflow.go` 分类上下文错误 | 优先采用契约和测试案例；支持能力按实际 endpoint/provider 确定，不能只看 Messages、Chat Completions、Responses 名称；不要照抄所有字符串匹配规则 |
| 恢复策略集中 | `internal/agent/query/loop/recovery_rules.go` 明确 max output、prompt too long、media error 等类别 | 优先采用：适配器负责识别，运行时负责恢复策略；限流、配额、取消、协议损坏不能都归为上下文溢出 |
| 权限决定有来源 | `permission/permission.go` 定义 Behavior、RuleSource、Decision、稳定错误码；`internal/tool/executor/permission_decisions.go` 按具体输入判定 | 优先采用：返回决定、原因、规则来源与资源范围，解释和执行共享结果；如果输入被修改，必须重新验证并明确授权覆盖范围 |
| 工具目录与执行分离 | `internal/tool` 下的 catalog、defaults、executor、builtin 分别承担发现、装配、执行与工具行为 | 采用责任边界；Kevin 只有出现相应职责时才拆模块，不预建四层空目录 |
| 生命周期与输入控制 | `client/runtime.go` 管理关闭、输入流及清理；`internal/agent/query/loop/queued.go` 管理中途输入 | 采用明确语义：补充输入、排队、取消和终止是不同操作；每项资源有唯一清理方。不要移植依赖文本前缀识别控制消息的方式，使用类型化事件 |
| MCP 边界 | `internal/mcp/client`、`config`、`sdkmcp` 区分客户端生命周期、配置与进程内服务 | 借鉴所有权分离；Kevin MCP 输出归一到现有工具/资源契约，并继续经过统一权限边界 |
| 环境依赖 | `internal/environment` 承担文件、媒体、网络、workspace 与用户交互等具体资源；公开 facade 与内部实现分开 | 采用“端口靠近责任所属模块”的原则，避免巨型 host/services 接口；保持宿主配置与凭据注入独立于内核策略 |

### nxs 也不能作为免验证的答案

- Go 的锁、goroutine、channel 和包导出习惯不应逐行翻译成 TS；需要解决的是相同的生命周期、竞态和背压问题。
- transcript 文件、恢复方法或关闭流程的存在，不证明崩溃恢复、exactly-once 或持久任务已经通过验收。本次未测试这些性质。
- 沙箱接口不代表所有操作系统具备同等隔离，文件、网络、进程能力需要分别验证。Kevin 此阶段仅保留必要边界，不上线原生沙箱实现。
- `cmd/nxs` 的进程协议、桥接、团队、AutoDream 和完整宿主产品能力不属于当前清理的默认范围。
- 不为了追随 nxs 的公开 facade，把已迁出的 legacy SDK 重新放回 core。是否提供外部 SDK，取决于明确消费者和版本契约。

## 两份参考如何分工

| Kevin 要解决的问题 | CC 主要贡献 | nxs 主要贡献 | 建议 |
| --- | --- | --- | --- |
| 多轮对话与压缩 | 保留什么、何时压缩、失败怎么办 | transcript/context/query 各自归属 | 先确立消息组和唯一历史来源 |
| 工具执行 | 并发、中断、结果预算等实际行为 | 发现、装配、执行和工具实现的边界 | 保留完整 turn 校验，逐项补调度契约 |
| 权限 | 实际资源与输入如何参与判定 | 稳定 Decision、来源和错误契约 | 优先消除解释与执行分叉 |
| 模型失败 | 历史循环描述的恢复场景 | provider 分类与 loop 策略分离 | 建立类型化失败与有限恢复表 |
| 用户介入 | 中途输入与 stop 的交互语义 | 会话输入流和资源生命周期 | 先定义接受、排队、取消、关闭语义 |
| Skill / MCP / Hook | 具体集成中的行为边界 | 独立集成模块与接线方式 | 服从 Kevin 统一权限，不开旁路 |
| 目录与产品功能 | 不作为目录模板 | 参考职责划分 | 按 TS 当前调用关系组织，按需拆分 |

## 后续实施顺序与验收条件

以下是待决策顺序，不是本次新增开发承诺；代码清理完成后先对照现有 P0–P6 验收记录去重。

1. **统一权限决定。** 对同一输入，解释、审批和执行得到一致结论；覆盖 MCP、Hook 修改、禁用工具和拒绝规则；输入变化不能复用不适用的授权。
2. **明确 session / run / request 投影。** 普通后续输入可以恢复合法历史；压缩和 rewind 不留下孤立 tool result；持久事实与请求预算投影分开。
3. **归一失败与恢复。** 为上下文超限、输出截断、媒体错误、限流、取消和损坏协议提供独立测试；恢复次数有界，取消后不再自动重试。
4. **完善工具生命周期。** 验证输入后再决定并发；副作用工具互斥约束明确；结果关联稳定；输出过大有可追溯处理；中断后资源释放。
5. **补齐输入与 Hook 终止语义。** 区分排队和取消；拒绝关闭后的新输入；清理不重复执行；Hook 超时、失败与阻止停止都有明确上限。

测试应覆盖可观察结果与失败路径，不为目录拆分、转发函数或 getter 添加形式化测试。确定性测试通过只能证明本地契约；真实模型、MCP 服务、进程异常与平台隔离仍需各自验收。

## 本次记录边界

仅新增本评估文档。未迁移参考源码，未修改 Kevin 内核，未启动沙箱或其他产品路线图工作。历史 Python 对齐计划也不作为当前 TypeScript 实现状态的证据。
