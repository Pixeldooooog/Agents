<div align="center">

<pre>
 █████╗  ██████╗ ███████╗███╗   ██╗████████╗███████╗
██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝██╔════╝
███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   ███████╗
██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   ╚════██║
██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   ███████║
╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚══════╝
</pre>

### 🚀 生产级 AI Agent 框架

**构建会思考、能行动、可学习的智能体**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

[快速开始](#-快速开始) • [核心功能](#-核心功能) • [架构设计](#%EF%B8%8F-架构设计) • [文档](#-文档) • [English](README.md)

</div>

---

## 🎯 Agents 是什么？

**Agents** 是一个基于**整洁架构原则**构建的 AI Agent 框架。

严格的分层边界。零隐式耦合。从第一天起就可读。

<table>
<tr>
<td width="33%" valign="top">

### 🏛️ **整洁架构**
严格的内核/平台/接口分层，零循环依赖

</td>
<td width="33%" valign="top">

### 🧠 **多模型支持**
统一接口对接 OpenAI、Claude、Gemini，协议无关的流式输出

</td>
<td width="33%" valign="top">

### 🛠️ **丰富工具生态**
内置文件操作、Git、Web 搜索、Shell 执行，支持 MCP 协议扩展

</td>
</tr>
<tr>
<td width="33%" valign="top">

### 🔒 **默认安全**
沙箱隔离、审批流程、工作空间隔离

</td>
<td width="33%" valign="top">

### ⚡ **实时流式**
实时显示文本、推理过程和工具调用

</td>
<td width="33%" valign="top">

### 🎨 **双界面**
开发者用终端 TUI，可视化用 Web UI

</td>
</tr>
</table>

---

## ⚡ 快速开始

```bash
# 克隆
git clone https://github.com/Pixeldooooog/Agents.git
cd Agents

# 安装
pip install -e .

# 配置（添加你的 API Key）
cp .env.example .env

# 启动终端界面
agents tui

# 或启动 Web 界面
agents gui
```

### 30 秒创建你的第一个 Agent

```python
from agents.kernel.specs import AgentSpec
from agents.kernel.runtime import AgentRuntime

# 定义能力
spec = AgentSpec(
    model="gpt-4",
    tools=["file_read", "web_search", "file_write"]
)

# 运行
runtime = AgentRuntime(spec)
result = await runtime.run("查找最新的 Python 最佳实践并生成总结")
```

**[📖 完整快速开始指南 →](docs/quickstart.md)**

---

## ✨ 核心功能

<details open>
<summary><b>🤖 多模型支持</b></summary>

通过统一接口无缝切换不同模型供应商：

```python
# OpenAI
spec = AgentSpec(model="gpt-4-turbo")

# Anthropic Claude
spec = AgentSpec(model="claude-3-5-sonnet")

# Google Gemini
spec = AgentSpec(model="gemini-1.5-pro")
```

所有模型都支持流式输出、工具调用和推理过程展示。

</details>

<details>
<summary><b>🛠️ 强大的工具系统</b></summary>

**内置工具：**
- 📁 文件操作（读/写/补丁）
- 🔍 文本与 Web 搜索
- 🌐 网页爬取与提取
- 🔧 Git 集成
- 💻 Shell 执行
- 🧪 测试运行器

**通过 MCP 扩展：**
```python
from agents.kernel.capabilities.tools import load_mcp_server

await load_mcp_server("./my_custom_tools.py")
```

</details>

<details>
<summary><b>✋ 人工审批流程</b></summary>

通过审批工作流控制敏感操作：

```python
spec = AgentSpec(
    model="gpt-4",
    tools=["file_write", "shell"],
    tool_approval_mode="ask",  # 执行前暂停并询问
    tool_permissions={
        "file_write": {"paths": ["/safe/dir/*"]},
        "shell": {"commands": ["git", "npm", "pytest"]}
    }
)
```

Agent 会暂停执行并通过 TUI 或 Web UI 等待你的审批。

</details>

<details>
<summary><b>🧠 记忆与上下文管理</b></summary>

长会话自动上下文管理：

```python
spec = AgentSpec(
    model="gpt-4",
    memory_enabled=True,
    context_window_tokens=128000
)
```

- 从历史会话中检索相关记忆
- 接近 token 上限时自动压缩上下文
- 重启后保持对话连贯性

</details>

<details>
<summary><b>🔒 沙箱隔离</b></summary>

工作空间隔离的安全执行：

```python
spec = AgentSpec(
    sandbox_mode="docker",  # 或 "local"
    workspace_id="project_alpha"
)
```

每个 Agent 都运行在受控的隔离环境中。

</details>

**[📚 完整功能文档 →](docs/features.md)**

---

## 🎨 界面

<table>
<tr>
<td width="50%">

### 💻 终端界面

```bash
agents tui
```

**为开发者打造：**
- 流式文本和推理显示
- 工具调用时间线
- 审批提示
- `@文件` 上下文注入
- 模型切换
- 命令历史

</td>
<td width="50%">

### 🌐 Web 界面

```bash
agents gui
```

**可视化工作空间：**
- 聊天界面
- 活动时间线
- 运行追踪检查器
- 审批控制
- 设置面板
- 工件查看器

</td>
</tr>
</table>

---

## 🏗️ 架构设计

**架构不是事后补充——它是基石。**

Agents 围绕严格的边界组织，使系统在成长过程中保持可理解、可测试、可维护。

<div align="center">

<pre>
┌─────────────────────────────────────────┐
│         Apps（终端 / Web）              │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│     Interfaces（HTTP/SSE, NDJSON）      │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│    Platform（会话、持久化）             │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│  Kernel（模型、运行时、工具等）         │
│  ✓ 零依赖于 Web/UI 层                  │
└─────────────────────────────────────────┘
</pre>

</div>

**设计原则：**
- 🎯 **关注点分离** — Kernel 是纯 SDK，不依赖 Web/UI
- 🔌 **协议无关** — 抽象不同模型供应商的差异
- 🔐 **安全优先** — 沙箱执行、密钥脱敏、审批门槛
- 📦 **可插拔存储** — 内存、JSON 或 SQLite 后端
- 🧪 **完整测试** — 核心组件全面测试覆盖

**[🏛️ 架构深度解析 →](docs/architecture.md)**

---

## 🎯 应用场景

<table>
<tr>
<td width="50%">

### 👨‍💻 **代码助手**
读取、分析、修改代码库，集成 Git

```python
spec = AgentSpec(
    model="claude-3-5-sonnet",
    tools=["file_read", "file_write", 
           "git_status", "patch_apply"]
)
```

</td>
<td width="50%">

### 📊 **数据流水线**
通过网页爬取获取、处理和分析数据

```python
spec = AgentSpec(
    model="gpt-4",
    tools=["web_search", "web_extract",
           "file_write"],
    skills=["data_analysis"]
)
```

</td>
</tr>
<tr>
<td width="50%">

### 🔧 **DevOps 自动化**
通过 Shell 监控、诊断和修复

```python
spec = AgentSpec(
    model="claude-3-5-sonnet",
    tools=["shell", "file_read"],
    tool_approval_mode="ask"
)
```

</td>
<td width="50%">

### 🔬 **研究助手**
搜索、总结、保持记忆

```python
spec = AgentSpec(
    model="gpt-4",
    tools=["web_search", "file_read"],
    memory_enabled=True
)
```

</td>
</tr>
</table>

**[📖 详细应用场景与示例 →](docs/use-cases.md)**

---

## 📚 文档

| 文档 | 描述 |
|------|------|
| **[快速开始](docs/quickstart.md)** | 安装、配置、第一个 Agent |
| **[功能详解](docs/features.md)** | 工具、模型、审批、记忆深度解析 |
| **[应用场景](docs/use-cases.md)** | 真实案例与完整代码 |
| **[配置说明](docs/configuration.md)** | 环境变量、配置文件、存储 |
| **[架构设计](docs/architecture.md)** | 系统设计与模块边界 |
| **[技术设计](docs/technical-design.md)** | 控制/数据平面与沙箱设计 |
| **[模块地图](docs/module-map.md)** | 模块职责与扩展点 |
| **[路线图](docs/roadmap.md)** | 开发计划与未来功能 |

---

## 🛠️ 开发状态

### ✅ **生产可用**

- ✓ 多模型流式输出（OpenAI、Claude、Gemini）
- ✓ 沙箱隔离的工具执行
- ✓ 带检查点/恢复的审批流程
- ✓ 终端和 Web 界面
- ✓ MCP 工具集成
- ✓ 记忆与上下文压缩
- ✓ SQLite 持久化与追踪

### 🚧 **即将推出**

- 多 Agent 编排（规划者/工作者/审核者）
- 托管账号系统与认证
- 沙箱池托管调度
- 高级浏览器自动化
- 计费与限流

---

## 🤝 贡献

欢迎贡献！请：

1. Fork 本仓库
2. 创建特性分支
3. 遵循[架构规则](docs/architecture.md#development-rules)
4. 为新功能添加测试
5. 提交 Pull Request

---

## 📄 License

MIT License - 详见 [LICENSE](LICENSE)

---

## 🌟 Star 历史

如果你觉得 Agents 有用，请给我们一个 Star！⭐

---

<div align="center">

**基于 FastAPI、Typer、Pydantic 和 MCP 用 ❤️ 构建**

[报告 Bug](https://github.com/Pixeldooooog/Agents/issues) • [功能建议](https://github.com/Pixeldooooog/Agents/issues) • [讨论](https://github.com/Pixeldooooog/Agents/discussions)

</div>
