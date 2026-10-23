# Python → TypeScript 迁移评估与执行方案

## 当前基线（2026-10-22）

评估对象是 `Agents` 主分支，不把旁边的实验 worktree 计入主分支完成度。

| 范围 | 文件数 | 代码行数 | 当前状态 |
| --- | ---: | ---: | --- |
| `src/**/*.py` + Python 入口/测试 | 518 | 93,601 | 主运行时、kernel、platform、server、bridge、SDK 仍在 Python |
| `apps/**/*.ts(x)` | 106 | 10,517 | terminal/web UI，terminal 仍通过 Python NDJSON bridge 运行 |
| `ts-core-spike` 的 `packages/` + `apps/` | 468 | 46,552 | 独立 TS runtime/host/UI 实现，尚未接回主分支 |

因此，主分支按“可替代 Python 运行时的实现”计，迁移完成度为 **0% 的 runtime、约 10% 的整体源码规模**。现有 TS UI 不代表 Python kernel 已迁移。实验 worktree 已覆盖完整 TS core/host，但它是迁移输入，不是主分支的验收结果。

## 目标架构

```text
apps/terminal  ─┐
apps/web       ─┼─> packages/host ─> packages/core
                │                    ├─ config / models
                │                    ├─ runtime / tools / permissions
                │                    ├─ store / tasks / sessions
                │                    └─ sdk / mcp / workspace
```

运行时、模型协议、状态存储和工具契约全部由 `packages/core` 提供；HTTP 和 terminal host 只负责适配；UI 不直接依赖内部 runtime。Python 在迁移期间只作为对照实现和回归参考，不再作为 TS 产品启动链的依赖。

## 执行阶段

### Phase 0：基线与边界（本次完成）

- 固化 Python/TS 文件和行数基线。
- 明确 `packages/core`、`packages/host`、`apps/*` 的 ownership。
- 把迁移分为 runtime、host、terminal bridge、web、验证与清理五条验收线。

### Phase 1：接入 TS core/host（本次开始）

- 将 `ts-core-spike` 的 `packages/core` 和 `packages/host` 接回主分支。
- 将 workspace 根脚本、锁文件和默认配置切换到 Bun/TypeScript 启动链。
- 保留现有 terminal/web UI 的用户可见行为，优先修复编译和导入边界。

验收：`bun run typecheck`、`bun test` 通过；HTTP host、terminal host 能在没有 Python bridge 的条件下启动。

### Phase 2：协议与产品入口切换

- terminal 从 Python NDJSON bridge 切换到 `packages/host/src/terminal`。
- web 从 Python FastAPI/SSE 路由切换到 `packages/host/src/api`。
- 对照现有 Python 测试，补齐 run、approval、session、task、MCP 和 workspace 的 TS 行为测试。

验收：terminal/web smoke、核心 API contract、持久化回放和 approval resume 均通过；启动脚本不再查找 Python executable 或 `agents.interfaces.*`。

### Phase 3：能力补齐与差异收敛

- 按领域逐项核对 Python 模块地图：config、models、runtime、tools、permissions、store、tasks、SDK、MCP、workspace。
- 每个领域保留一份 parity checklist 和 TS 测试；未实现能力必须显式标为 gap，不能用空实现伪装完成。
- 对模型 provider、sandbox、OAuth、远程 transport 等外部依赖做独立集成验证。

验收：核心能力清单无未标记 gap；本地单元测试、协议测试、UI smoke 和真实 provider 验证分层报告。

### Phase 4：Python 下线与发布验收

- 删除 Python runtime、bridge、FastAPI/Typer 入口和 Python packaging 文件。
- 更新 README、quickstart、部署文件和 CI，只保留 Bun/TypeScript 路径。
- 在干净 checkout 执行安装、构建、测试和启动验收。

验收：仓库运行时源码不再包含 Python；`rg` 不再命中 Python 启动链；干净环境可以完成 build/check/smoke。

## 验收口径

1. **静态边界**：无跨层反向依赖；入口文件只做 wiring；核心模块有明确目录归属。
2. **类型与单元测试**：TypeScript 编译无错误，core/host 测试通过。
3. **协议回归**：HTTP、terminal NDJSON、事件流、approval、session/task 持久化通过。
4. **产品 smoke**：web 构建、terminal render/interaction/app smoke 通过。
5. **运行时验收**：至少完成一次真实 provider 请求；无 key/网络/额度等外部失败要单独标注。
6. **清理验收**：最终删除 Python 前，先确认 TS 启动链、数据格式和迁移/回滚说明完整。

## 当前风险

- `ts-core-spike` 的 worktree 元数据指向已不存在的路径，当前目录只能作为文件输入，不能直接依赖其 Git 状态。
- 本机没有 `bun`，因此 TS 验收需要先安装/提供 Bun；在此之前只能完成静态审计和代码接入，不能声称构建或运行时验收通过。
- Python 主分支在实验分支共同祖先之后还有多轮能力提交；接入 TS 后必须对照最新 Python 模块和测试逐项检查，不能只按文件数量宣布完成。
