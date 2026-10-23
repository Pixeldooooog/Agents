# Agents

Agents 是一个 TypeScript-first 的 agent runtime：后端使用 Bun/TypeScript，终端使用 Ink/TypeScript，Web 使用 Solid/TypeScript。

[![TypeScript](https://img.shields.io/badge/typescript-5.x-blue.svg)](https://www.typescriptlang.org/)
[![Bun](https://img.shields.io/badge/runtime-bun-black.svg)](https://bun.sh/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 快速开始

```bash
git clone https://github.com/Pixeldooooog/Agents.git
cd Agents
bun install

cp .env.example .env

bun run tui
bun run web
```

默认 HTTP 服务地址是 `http://localhost:8020`，Web UI 挂载在 `/ui/`。

## 项目结构

```text
apps/
  terminal/    Ink 终端界面
  web/         Solid 浏览器界面
packages/
  host/        Bun HTTP 宿主、静态 Web 挂载、终端 host 进程
  core/        共享 runtime、模型配置、状态、任务和工具契约
config/        非 secret 默认配置
deploy/        容器和 compose 入口
```

`apps/*` 放产品入口，`packages/*` 放共享 runtime/domain 代码。入口文件保持薄，具体行为拆到语义明确的小模块里。

## 常用命令

```bash
bun run server        # 启动 TS HTTP 后端
bun run terminal-host # 启动终端 host 进程
bun run tui           # 启动终端界面
bun run web           # 构建 Web 并由后端托管
bun run dev-web       # 后端 + Vite 开发服务
bun run typecheck     # core/host/terminal 类型检查和 Web 构建
bun run test          # 运行 TS 测试
bun run check         # 完整本地验证
```

`makefile` 也映射到同一套 TS 命令：

```bash
make setup
make check
make build
make up
```

## Runtime 边界

- `packages/core/src/config/settings.ts` 读取 TOML/env 配置。
- `packages/core/src/models/modelProfiles.ts` 构建命名模型 profile。
- `packages/core/src/runtime/agentRuntime.ts` 执行模型回合并产出统一事件。
- `packages/core/src/store/jsonStateStore.ts` 持久化 run 和 task JSON 状态。
- `packages/host/src/api/agentRoutes.ts` 暴露 HTTP API。
- `packages/host/src/terminal/main.ts` 暴露终端 host 进程。

## 模型配置

在 `.env` 或 shell 环境里配置 provider：

```bash
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o

AGENT_CLAUDE_API_KEY=...
AGENT_CLAUDE_MODEL=claude-opus-4-7

GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.5-pro
```

OpenAI-compatible 自定义 profile：

```bash
AGENT_MODEL_PROFILES=kimi
AGENT_MODEL_PROFILE_KIMI_PROTOCOL=openai-chat
AGENT_MODEL_PROFILE_KIMI_BASE_URL=https://api.moonshot.cn/v1
AGENT_MODEL_PROFILE_KIMI_MODEL=kimi-k2
AGENT_MODEL_PROFILE_KIMI_API_KEY=...
```

终端内用 `/model` 切换 profile。

## 文档

- [Quickstart](docs/quickstart.md)
- [Architecture](docs/architecture.md)
- [Configuration](docs/configuration.md)
- [Module Map](docs/module-map.md)
- [Features](docs/features.md)
