# nexus-code 整体审查与 Kevin 借鉴边界

日期：2026-10-26。参考仓库：工作区同级 `../nexus-code`，HEAD `13ef6bf`。

## 结论与来源更正

用户确认 nexus-code 是此前迁移、补全的一套 CC 风格实现。因此，不能把目录名 `src-origin` 当作官方来源证明，也不能把 `src` 中补齐的接口当作完整功能。此前 [参考评估](kernel-reference-assessment.md) 中对“CC 成熟行为”的表述应按此更正。

**该项目具有实际运行骨架，也包含实质性的本地补全，但目前不适合作为 Kevin 内核的正确性基准或整体移植对象。** 可以提取设计问题、协议 fixture、工具行为约束；不能按文件数、构建成功或功能名称判断完成度。

本次覆盖目录差异、构建与测试入口、模型适配、query/上下文、工具和权限接线、Skill/MCP/Hook 边界及补全模块抽查。不是对两千多个文件的逐行安全审计，未进行真实 provider、MCP 服务、交互终端或跨平台沙箱验收。

下文源码路径均相对 nexus-code；该仓库已经移到 Kevin 同级，不是 Kevin 生产代码的一部分。

## 高优先级发现

### 1. [P1] Chat Completions 多工具调用复用内容索引

位置：`src/services/api/openai-adapter.ts:1045–1071`，消费端 `src/services/api/claude.ts:2051–2110`。

新 tool call 写入 `currentToolCallIds` 时使用当前 `contentBlockIndex`，但没有为下一调用分配新索引；只有结束文本块或处理 finish 时才递增。模型在同一响应产生两个工具调用时，两者都可能使用索引 0。消费端按 `contentBlocks[part.index]` 保存内容，后来的 start 覆盖前一个调用，后续参数也指向相同槽位。

这会破坏工具名、调用 ID 和参数的对应关系。应在分配新块时立即保留唯一索引，并测试同一 chunk 多调用、跨 chunk 交错参数和文本/工具交替。证据：静态生产者—消费者调用链；本次未执行该路径的端到端复现。

### 2. [P1] Chat usage 尾事件覆盖真实停止原因

位置：`src/services/api/openai-adapter.ts:999–1020`、`1088–1117`；消费端 `src/services/api/claude.ts:2298–2303`。

请求启用了 `include_usage`。如果 provider 在 `finish_reason=length` 或 `tool_calls` 后发送空 choices 的 usage chunk，适配器会再发送一个 `stop_reason=end_turn`。消费端无条件把最新 stop reason 写回最后一条消息，覆盖此前的 max_tokens/tool_use。

至少会损坏最终消息与 transcript 的终止原因，并可能使依赖该字段的恢复策略失效；不据此断言所有工具执行都会停止。应把 usage 更新与停止原因分离，并验证尾 usage 不改变既定结束状态。证据：静态调用链。

### 3. [P1] Responses 缺失终止事件时被补成成功

位置：`src/services/api/openai-adapter.ts:1551–1574`。

当事件迭代器结束而未收到 completed/incomplete 时，代码主动构造 completed，再产生 message_stop。已经通过导出的 `streamOpenAIResponsesForTest` 注入空事件数组复现，输出为：

```text
message_start → message_delta(stop_reason=end_turn) → message_stop
```

这会把空响应或没有明确终态的流伪装成正常完成；有工具块时还可能补成 tool_use。应要求合法终态，缺失终态返回明确的协议中断错误；用户取消保持独立结果。这是本地 mock 复现，不是实际 provider 网络断流测试。

### 4. [P2] OpenAI 模型菜单仍依赖 Anthropic 认证

位置：`src/utils/model/modelOptions.ts:339` → `src/utils/auth.ts:136`、`286`；对应 `src/utils/model/modelOptions.test.ts:60`。

配置 OpenAI 后，模型菜单仍先执行 Anthropic 订阅判断；在本次测试环境没有 Anthropic 凭据时抛出必需凭据错误。现有测试直接复现，导致 47 个测试中 1 个失败。应让 provider 的菜单和认证判断独立，而不是要求用户额外配置另一家凭据来绕过错误。

## 补全代码的真实性分层

`src` 共 2,124 个文件，`src-origin` 共 1,903 个文件；共有路径中 461 个内容不同，新增 236 个，移除 15 个。统计包含资源与 `.DS_Store`，不代表实现规模或完成率，也不能证明每个差异由谁产生。

| 层级 | 样例与观察 | 判定 |
| --- | --- | --- |
| 实际可构建骨架 | CLI、QueryEngine、query、主要内置工具、协议调用和 UI 已有大量实现 | 可以沿调用链阅读；构建成功不等于行为正确 |
| 有实质逻辑的补全 | `services/api/openai-adapter.ts`、`services/skillSearch/remoteSkillLoader.ts` | 有协议转换/获取缓存等真实逻辑，但仍需边界测试；不能统称为空壳 |
| 显式关闭的能力 | `services/compact/reactiveCompact.ts` 的 enabled/withheld 固定 false；`services/contextCollapse/index.ts` 同样固定关闭 | 当前不提供这些恢复能力，不应计入“完成” |
| 无操作实现 | `services/sessionTranscript/sessionTranscript.ts` 两个写入方法直接 resolve；`daemon/main.ts` 为空函数 | 分段 transcript / daemon 不成立；不能因此断言项目其他 transcript 持久化也不存在 |
| 工具占位 | Monitor、Workflow 返回 unavailable；ReviewArtifact、WebBrowser、Snip、REPL 返回 `ok:false` | 有些受 feature gate 控制，不一定默认暴露；启用开关不能使其成为可用工具 |
| 部分近似实现 | `services/compact/snipCompact.ts` 按消息数与估算 token 裁剪；`snipProjection.ts` 只过滤边界标记 | 没有看到按工具调用组对齐裁剪点，也没有按 removedUuids 重放删除范围；不适合直接采用 |
| 转发适配 | `vendor/nexus-sdk/index.ts` 转发 Anthropic SDK；sandbox 同样转发外部包 | 是命名/兼容层，不是独立实现或已验证的隔离能力 |

### 关闭能力背后的契约仍然不一致

`query.ts:1121–1150` 将 `tryReactiveCompact` 的 truthy 返回值传给 `buildPostCompactMessages`；后者要求 boundaryMarker、summaryMessages、attachments、hookResults 等字段。补全函数却返回 `{messages, compacted:false}`，且没有接受调用处的完整选项。

当前 fixed-false 判断通常阻止进入该路径，所以不把它列为默认可复现故障。但是未来仅打开 feature 或 enabled 开关，会暴露契约错误；不能“启用后再看看”。应先定义一致的成功/未执行/失败联合类型，再实现或显式移除该能力。

`scripts/build.ts` 的 dev-full 只是手工列举的一组开关，未包含所有源码 feature（例如 REACTIVE_COMPACT、CONTEXT_COLLAPSE、HISTORY_SNIP、DAEMON）。因此 dev-full 构建通过不覆盖上述所有路径。

## 工程边界评估

1. **协议中立性不足。** OpenAI 转换到内部 Anthropic Beta 类型，并复用 `claude.ts` 处理。适合作为已有项目接入另一 provider 的兼容策略，不适合作为 Kevin 多协议内核的长期契约。Kevin 应使用自有类型，分别适配三种协议。
2. **工具接口混入 UI。** `Tool.ts` 同时定义工具执行、权限与 React 渲染；工具业务和终端表现不易独立复用。借鉴输入验证与并发约束，拆开 UI 展示职责。
3. **装配与策略体积过大。** query 约 1,730 行，claude API 约 3,497 行，hooks 约 5,023 行。行数不是独立缺陷，但这些文件横跨策略、协议和生命周期，不能作为“清晰 TS 分层”的模板。
4. **类型检查不能由打包替代。** `tsconfig.json` 设置 strict=false，package scripts 没有 typecheck，项目没有固定自己的 TypeScript 开发依赖。Bun 打包不执行完整类型检查，因此占位模块可以在导入完整、构建通过时保持契约错误。
5. **权限和扩展必须遵从 Kevin 已定规则。** 可参考输入验证、资源范围与 deny/ask/allow 的设计，但不能继承 Skill allowedTools 自动增权或隐式 shell 执行路径。MCP transport 与 Hook 生命周期仍需经过统一执行授权。
6. **命名不能充当安全保证。** 例如 `bridge/webhookSanitizer.ts` 实际原样返回内容。未在本次证明可利用路径，但不能把该函数名当作已经完成内容隔离的证据。

## 本次验证

| 检查 | 结果与界限 |
| --- | --- |
| missing import 脚本 | `TOTAL_MISSING=0`；仅证明该扫描器能找到引用路径，不证明接口一致或所有依赖可用 |
| 普通 build | 成功，4,791 个模块；本机已有依赖环境 |
| dev-full build | 成功，4,837 个模块；只覆盖脚本选择的 feature 集 |
| 构建产物 `--version` | 能启动，显示 `0.0.0-dev (Nexus Code)`；与 package 的 `0.1.0` 不一致，版本注入/回退仍需核对 |
| `bun test` | 46 pass、1 fail，47 tests / 12 files；失败为上述 OpenAI 模型菜单认证耦合 |
| 空 Responses 事件流 | 本地 mock 确认被补成正常结束 |
| 类型检查 | 参考项目未固定编译器；借用 Kevin 的 TypeScript 5.9.3，原配置先因 ignoreDeprecations=6.0 不兼容而失败；随后仅以命令行覆盖该选项继续检查，仍有缺失类型声明和接口不匹配诊断；不能将这些混合诊断全部算成业务缺陷，也不能冒充项目正式 typecheck |

现有测试集中在命名、配置、登录、模型选择、analytics 禁用及 Responses 转换；没有据此证明 query 恢复、权限、MCP、Hook、工具并发和崩溃恢复已受完整回归保护。本次构建只生成参考仓库的 dist 产物，没有修改生产源码。

## Kevin 可以借鉴什么

| 对象 | 保留的价值 | 采用前条件 |
| --- | --- | --- |
| QueryEngine/query 的行为描述 | session、run、工具结果、恢复、停止的场景清单 | 从场景写独立测试，不整体搬运循环 |
| 工具行为声明 | 输入 schema、只读/副作用、并发、中断、输出预算 | 去 UI 化，实际输入参与判定，统一权限入口 |
| OpenAI fixture | failed 事件、最终 arguments、隐藏 reasoning 的回放案例 | 补上多工具交错、usage 尾事件、空流、截断、取消、fallback 边界 |
| 上下文预算思路 | 压缩前控制工具结果，有限恢复，保留边界 | 使用合法消息组，禁止基于裸消息条数裁断调用/结果 |
| 本地补全经验 | 明确哪些旧接口依赖不可用的产品服务 | 对不支持能力明确报 unsupported 或不注册，避免静默空实现 |
| nxs 的职责组织 | context、session、provider、executor、runtime 分离 | 仍需逐项验证；不是因为 nexus-code 有问题就自动证明 nxs 正确 |

建议把 nexus-code 定位为**历史实验与场景参考库**。Kevin 的 P0–P6 验收标准来自自身契约和可重复测试；优先继续统一权限、合法历史投影、协议终态与工具执行边界。当前不建议为借鉴而修复 nexus-code 的全部旧功能，也不把本审查转成新一轮大规模迁移任务。
