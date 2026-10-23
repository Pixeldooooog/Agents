# Python → TypeScript 迁移评估与执行方案

## 最终目标

仓库运行时由 Bun/TypeScript 提供，产品入口统一落在 `apps/*` 和 `packages/*`；Python runtime、Python bridge、FastAPI/Typer 入口及 Python packaging 不再属于仓库实现。

```text
apps/terminal  ─┐
apps/web       ─┼─> packages/host ─> packages/core
                │                    ├─ config / models
                │                    ├─ runtime / tools / permissions
                │                    ├─ store / tasks / sessions
                │                    └─ sdk / mcp / workspace
```

## 迁移检查点

| 检查点 | 结果 |
| --- | --- |
| 初始主分支 | 518 个 Python 文件、约 93,601 行；TS/TSX 106 个文件、约 10,517 行；terminal 依赖 Python bridge |
| TS runtime 接入 | 已完成：`packages/core`、`packages/host`、TS terminal host 和 Bun workspace 已接入 |
| 产品启动链切换 | 已完成：HTTP host、terminal host、Web、terminal smoke 均走 TypeScript |
| Python runtime 下线 | 已完成：`src/`、`tests/`、`pyproject.toml`、`requirements/`、`main.py` 和 legacy `old/` 已删除 |
| 发布入口切换 | 已完成：CI、Dockerfile、compose、Makefile、README 和 quickstart 使用 Bun/TS |

当前主分支保留的 Python 字样只出现在兼容协议测试名称、Notebook 语言默认值和历史设计文档中，不是运行时依赖或启动入口。

## 已执行的实现

- 将 TS core/host 从 `ts-core-spike` 接入主分支。
- terminal 从 Python NDJSON bridge 切换为 `packages/host/src/terminal`。
- Web 从 Python server 切换为 `packages/host/src/api`。
- 根目录改为 Bun workspace，`bun run check` 只运行 core、host、Web 和 terminal 验证。
- 默认配置切换到 TS host schema 和完整 builtin tool registry。
- CI 使用 `oven-sh/setup-bun`；Docker 使用 Bun build/runtime 镜像。
- 删除 Python runtime、Python tests、Python packaging 和旧 fallback 目录。

## 验收口径

1. **静态边界**：源码只保留 `packages/core`、`packages/host` 和 `apps/*` 的 TS/TSX runtime；无 `agents.interfaces.*`、FastAPI、Typer 或 Python 启动脚本。
2. **类型与构建**：core、host、terminal 类型检查通过，Web production build 通过。
3. **协议回归**：core/host 测试覆盖 run、approval、session、task、MCP、SDK JSONL/SSE/WebSocket、workspace 和工具注册。
4. **产品 smoke**：terminal render、interaction、app smoke 通过；HTTP host 和 terminal host 可启动。
5. **发布入口**：CI 和 Docker 使用 Bun；干净环境只需 `bun install` 即可执行 `bun run check`。
6. **外部依赖**：真实 provider 请求仍需使用实际 API key 和网络环境单独验证；本地验收不把 provider 额度、网络或认证状态误报成代码通过。

## 后续维护

- 新能力只进入 `packages/core` 或 `packages/host`，禁止重新引入 Python runtime。
- 兼容 `src-origin` 的字段可以保留在 TS SDK contract 中，但实现必须落在 TS canonical domain module。
- 真实 provider、Docker clean-host、签名发布和生产部署属于独立发布门禁，应在对应环境执行。
