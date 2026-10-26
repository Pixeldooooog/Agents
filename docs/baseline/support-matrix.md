# 当前验证范围与支持矩阵

2026-10-26；环境证据只覆盖本次实测，不由交叉编译推断平台可用。

| 范围 | 当前证据 | 交付边界 |
|---|---|---|
| macOS arm64 / Bun 1.4.4 | 本地 core/host/terminal 回归，Shell 进程组终止测试 | LocalExecutor 开发基线；不提供安全隔离 |
| Linux x64 | 仓库已有 ubuntu CI；本批尚未运行远程 CI | 待 CI/目标机验证；不把 macOS 测试当作 Linux 通过 |
| Windows | 预留 executor 后端 | 当前本地命令明确不支持；MXC 与进程监督独立验收 |
| macOS/Windows/Linux 原生沙箱 | 类型/策略接入点，isolated 请求失败关闭 | 按用户决定暂缓；不阻塞其他基线 |
| HTTP loopback | token、Origin、Host 与写入测试 | 无 token 是受限本地模式，无法阻止本机进程访问 |
| HTTP 非 loopback | 强制配置 token，策略测试 | 实际 TLS/反向代理部署待验收 |
| Docker | 既有可选部署镜像路径 | 当前本机 daemon 未运行，未验证镜像；不是桌面前置依赖 |
| OpenAI Chat/Responses、Claude Messages、Gemini | 当前 TS 协议实现及选定 fixture 测试 | 真实账号/模型、多模态、超时和额度独立验收 |
| MCP/Browser/LSP | 当前适配与选定本地测试 | 实际服务/权限/生命周期待验收 |
| Memory/Artifact/后台 Routine | 当前接口和部分旧功能 | Markdown 事实源、可追溯产物、常驻触发按 B2/B3 继续 |

迁移清单：`migration-inventory.json` 映射旧 revision `b0d90f08cf3b1d1e3634c604942c7e019d1e7d91` 下全部 450 个 `src/agents` Python 文件到 31 个领域，标明候选 TS 位置与缺口。包标记单独列出。静态提取的 37 个注册工具名在当前 120 个工具中均存在；这只是指定注册函数的字面量名称匹配，未包含动态别名，也不证明参数/错误/副作用等价。脚本会对未映射文件或不存在的 TS 目标报错。

复现：`bun --no-env-file scripts/baseline/migration-inventory.ts --check`。更改旧 revision、领域映射或工具描述时，重新生成并审查差异。尚未完成完整行为等价验收。
