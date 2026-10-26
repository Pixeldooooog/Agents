# 第二批：执行生命周期与工具边界

日期：2026-10-26；B1 进行中。按用户最新决定，原生沙箱独立暂缓，其他 PRD 基线继续实施。

## 已接入运行链的改动

| 范围 | 行为变化 | 证据 |
|---|---|---|
| CommandExecutor | 独立 port、可信策略、后端能力；当前仅 LocalExecutor | isolation 请求在 executor 和工具入口均拒绝，不回退 |
| 前后台 Shell | 统一监督，有限输出/时长，TERM→KILL、后台记录容量 | 真实本地子进程与孙进程忽略 TERM，超时/取消/后台 kill 后不再运行 |
| Runtime 取消 | RuntimeOptions 的 signal 传到工具与执行器 | Shell 启动后中断，后续测试文件未写入 |
| 工具参数 | 120 个内置工具均要求显式 schema，Ajv 在 handler 前校验，不自动转换类型 | 错误类型、大输入不会产生文件副作用；全量旧测试回归 |
| 工具返回 | 限制序列化返回大小；大结果保留成功语义，返回有效 JSON 截断预览 | Unicode、控制字符、前后台大输出测试 |
| 工具权限 | 未启用/已禁用工具无法通过 runtime dispatch；审批恢复重新检查 | 未授权写入未发生，模型别名也受限制 |
| 审批要求 | auto 模式不再忽略显式 approval_required_tools | fixture 模型返回写操作后进入 awaiting_approval，文件未写入 |
| 后台查询 | 输出按 UTF-8 字节截断，移除不存在的 output_path | 小字节窗口输出与真实累计字节数验证 |
| 迁移定位 | 全部 450 个旧 Python 文件归入 31 个领域，注明 TS 目标与缺口 | 可复现 inventory --check；37 个静态注册名称匹配，非语义等价 |

核心位置：`packages/core/src/ports/commandExecutor.ts`、`execution/`、`tools/toolValidation.ts`、`tools/toolOutput.ts`、各领域 schema 文件、`runtime/runtimeToolPermissions.ts`。注册文件仅组合定义和执行边界，不承载进程监督细节。

新增依赖：core 的 Ajv 8.17.1，lockfile 同步。schema 编译在工具注册时完成；错误声明导致启动失败，不在调用时悄悄忽略。

## 验证

环境：macOS arm64，Bun 1.4.4；源码为当前未提交工作区。

```sh
bun --no-env-file test packages
bun --no-env-file --bun run --cwd packages/core typecheck
bun --no-env-file --bun run --cwd packages/host typecheck
bun --no-env-file --bun run --cwd apps/terminal typecheck
bun --no-env-file --bun run --cwd apps/web build --outDir /tmp/kevin-b1-web-build
bun --no-env-file --bun run --cwd apps/terminal render-smoke
bun --no-env-file --bun run --cwd apps/terminal interaction-smoke
bun --no-env-file --bun run --cwd apps/terminal app-smoke
bun --no-env-file scripts/baseline/migration-inventory.ts --check
bun --no-env-file scripts/baseline/sqlite-spike.ts
```

全量测试：201 pass / 0 fail，32 个测试文件，1187 个断言。测试使用临时目录、fixture 模型和真实本地子进程，不调用付费模型。Core/Host/Terminal 类型检查、Web production build、Terminal render/interaction/app smoke、SQLite spike、迁移清单 --check 全部通过。Web 输出临时目录，未改动跟踪的 dist。`git diff --check` 通过。未运行真实 Provider、远程 CI、Linux/Windows 实机测试；未提交、推送或部署。

## 尚未完成

- 原生沙箱后端按用户决定暂缓；当前继承宿主环境，不能宣称文件/网络/凭据隔离。Windows 命令执行未启用；Linux 本批没有实机结果。
- schema 的存在和运行时校验不等于每个工具的业务约束都已完备。Git 子操作、MCP/Workflow 内部派发、动态别名等仍需逐条授权与语义审计；不是完整 Grant/Action Ledger 的替代。
- 通用返回限额发生在 handler 返回后，不限制 handler 读取大文件、正则搜索或第三方响应过程中的峰值内存/CPU。需逐工具继续补 streaming、deadline、取消。
- 目前命令取消接通 Runtime/SDK signal；Task.cancel 仍缺持久 cancel_requested 与副作用核对。B2 持久任务、队列/lease、SQLite adapter、预算和恢复尚未完成。
- 真实模型/MCP、完整旧版等价、常驻服务、Memory Markdown 与 Artifact/恢复验收按 PRD 继续。

这批完成的是可测试的执行边界增量，不代表 B1 或整个基线已验收。
