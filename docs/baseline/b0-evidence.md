# B0 首批实现与证据

日期：2026-10-26。执行环境：macOS arm64 / Bun 1.4.4。状态：**B0 进行中，B1–B3 尚未验收**。

## 本批落地

- `@agents/core/contracts` 提供 schema v1 的 Task / Run / Action / Checkpoint / Grant / Approval / Event / Input / Goal / Plan / Routine 契约。纯函数检查状态转换、租约 epoch、授权/审批绑定和副作用恢复决策。旧 runtime 尚未切换，不能将类型声明算作持久执行实现。
- 抽出 `core/src/ports` 的七类 StateStore 接口；runtime、工具、Task、SDK 依赖接口。默认适配器仍为 JSON，接口不提供事务、租约或原子 outbox 保证。
- Host 默认 loopback、显式 Origin、远程绑定强制 token；防止浏览器跨站写入和 loopback DNS rebinding。静态 UI / health 无敏感信息可匿名读取。首次本地 token 配置尚未实现。
- 工具循环默认 40 轮，请求只能降低上限。尚无持久 token/cost/time 预算。
- 固定开发/CI Bun 1.4.4；Docker 基础镜像仍为浮动 Bun 1，暂不属于固定版本验收环境。

## 能力映射与后续门槛

| 能力 | 当前实现/本批证据 | 未完成门槛 |
|---|---|---|
| K01 TS 基线 | core/host/terminal 已有主链；独立 contracts 与回归 | Python→TS 每个 API/异常/流事件等价表尚未全量审核 |
| K02 模型协议 | core/providers 及现有协议测试 | 真实 Provider 能力、错误路径与多模态验收 |
| K03 上下文 | context/session/SDK 回放及压缩测试 | scope 与长对话约束验收 |
| K04 工具 | toolRegistry 注册文件、搜索、补丁、Git、进程、Web、浏览器、Notebook、LSP、worktree、MCP、扩展、协作、Task、schedule、Memory、planning、session、权限、hook、结构化输出、配置、交互、命令、prompt、workflow | 逐工具 schema、输出边界、取消与 replaySafety 迁移；并非只有 read/list |
| K05 授权 | 纯函数拒绝旧租约、撤销、参数/账户变化、预算不足 | 真实 dispatch 边界集成、授权持久化、不可信输入测试 |
| K06 隔离 | macOS 临时策略实测 | 生产 allowlist、路径/符号链接、SSRF、子进程残留、Linux；现有 Shell 仍宿主执行 |
| K07 存储 | StateStore 解耦；SQLite spike | SQLite adapter/importer、磁盘满/只读/损坏处理、迁移协议 |
| K08 调度 | RunLease 契约 | 持久队列、领取事务、单 active Run、旧 worker fencing |
| K09 恢复 | unknown 阻止完成/取消；非重复动作需人工核对 | Action Ledger/checkpoint/outbox 与崩溃注入 |
| K10 用户介入 | InputCommand 契约 | cancel_requested 持久化、进程停止、消费游标 |
| K11 预算 | 有限工具循环 | 持久预算账本、等待释放 lease、跨 Task 配额 |
| K12 主动任务 | Routine 的 DST/漏跑/重叠字段 | 常驻服务、休眠重启、后台触发验收 |
| K13 Memory | 旧 JSON Memory；目标 Markdown 事实源 | Markdown 编辑冲突、元数据索引、删除/重建 |
| K14 Artifact | Checkpoint 引用契约 | 内容存储、哈希、来源、路径约束 |
| K15 客户端边界 | HTTP 网络回归与版本化 Event 类型 | 统一服务所有权、持久事件 replay、过期游标重同步 |
| K16 备份恢复 | 无活跃调度的 SQLite 快照在新进程打开 | 全量正文/文件/凭据恢复、冻结调度、外部动作核对 |
| K17 个人策略 | Goal/Plan/Routine 类型 | 三类个人场景与完成证据贯通 |
| K18 外部验收 | 本地回归 | 真实模型/MCP、部署、凭据与诊断脱敏 |

## 可复现命令

从仓库根目录执行（Bun 1.4.4）：

```sh
bun --no-env-file test packages
bun --no-env-file --bun run --cwd packages/core typecheck
bun --no-env-file --bun run --cwd packages/host typecheck
bun --no-env-file --bun run --cwd apps/terminal typecheck
bun --no-env-file --bun run --cwd apps/web build --outDir /tmp/kevin-b0-web-build
bun --no-env-file --bun run --cwd apps/terminal render-smoke
bun --no-env-file --bun run --cwd apps/terminal interaction-smoke
bun --no-env-file --bun run --cwd apps/terminal app-smoke
bun --no-env-file scripts/baseline/sqlite-spike.ts
bun --no-env-file scripts/baseline/macos-isolation-spike.ts
```

两个 spike 只使用临时测试目录并在结束时清理。SQLite 验证 WAL、外键、同步事务/迁移回滚、双连接写锁、静态快照和新进程重新打开；不模拟工具成功后崩溃。隔离脚本有未隔离的正向对照，只拒绝指定测试文件和网络，不能作为可部署的通用安全策略。

初始回归 184 pass / 1 fail：SDK session 排序测试假定快速操作具有不同毫秒时间戳。本批为该测试注入单调递增时钟并在 finally 恢复，未改变生产排序语义。

## 后续接入顺序

先完成旧能力映射与支持矩阵、Linux 隔离 spike，关闭 B0 剩余项。B1 将工具元数据/schema/输出限制、授权和 executor 接入真实运行边界；B2 才引入 SQLite adapter 与队列/lease/Action Ledger/checkpoint/outbox 原子写入。避免直接把旧 JSON 字段改名后宣称持久化完成。每阶段保持旧协议兼容适配，迁移必须有失败回滚证据。

## 本批最终验证结果

- 全量测试：189 pass / 0 fail，30 个文件、1119 个断言。
- SDK 单独复测：18 pass / 0 fail。第二处 session replay 测试也存在同毫秒排序假设，采用相同的确定性时钟；生产环境同时间戳排序语义仍需后续游标/序号契约统一。
- Core / Host / Terminal TypeScript 检查通过。新增 Host 测试使用显式 Bun 类型；开发依赖与 lockfile 同步。
- Web TypeScript + Vite 构建通过，输出临时目录，未改动已跟踪的 dist。
- Terminal render / interaction / app smoke 全部通过（fixture，本批未调用真实模型）。
- SQLite 与 macOS 隔离 spike 通过，具体覆盖和局限见上文。
- `git diff --check` 通过。本批没有提交或推送，也没有部署。


## 2026-10-26 后续更新

本记录以上内容为首批快照。用户随后明确暂缓原生沙箱上线：Linux/其他平台隔离不再阻塞其他内核工作。现已补 [逐文件迁移清单](migration-inventory.json)、[支持矩阵](support-matrix.md) 和 [执行器 ADR](adr-001-local-execution.md)。完整行为等价仍待审核，不能将静态覆盖当作迁移验收。第二批执行与工具边界进展见 [B1 证据](b1-execution-evidence.md)。
