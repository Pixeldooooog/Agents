# 内核集成与本轮验收

范围为 `kernel-boundaries.md` 的 P0–P6，不包括产品路线图 B2 的持久任务恢复、云端部署或已暂缓的原生沙箱。此前 P0–P3 记录保留；本文件说明本轮 P4–P6 实现及证据，不将本地测试等同线上验收。

## MCP

- 固定使用 `@modelcontextprotocol/sdk@1.32.2`。支持 stdio 和 Streamable HTTP；其他历史配置 transport 在 Host 装配时明确拒绝。
- stdio 使用独立 executable/args，不通过 shell 拼接；默认继承 SDK 最小环境。进程 stderr 不直接输出到产品日志。HTTP 禁止重定向，单响应/stdio 单消息上限 8 MiB。
- 发现最多 64 页、1,024 项；重复游标、重复工具名称、无效 object schema 显式失败。
- 外部工具名称由 server/name/schema/description 摘要生成，不与内置名称冲突。工具定义变化产生新 ID，旧审批不能静默调用新定义。模型侧仍看到来源描述。
- 发现不授予调用权限。用户必须把 status 中的工具 ID 加入 enabled_tools；外部工具调用每次需要审批，参数、权限、取消、输出限制经过公共工具执行器。
- 连接断开会撤销旧 provider；只能显式重连，绝不自动重放有副作用的调用。SDK consumer 应保留 Host-owned provider 数组并在关闭时释放。
- Plugin enable/disable 同样只改变状态，不修改 enabled_tools。

Host 在 config TOML 的 `[mcp]` 读取 `server_name`、`server_transport`、`server_command`、`server_args`、`server_url`、`server_headers`、`client_timeout`。stdio 的 command 是可执行文件，参数放在数组中。Host 启动不会自动启动 MCP 进程。

1. `GET /api/v1/agent/mcp` 查看受信配置和连接状态。
2. `POST /api/v1/agent/mcp/:name/reconnect` 显式连接/重连。此入口受 Host 原有认证与 Origin 检查保护，不接受 executable/URL 参数。
3. status 返回实际工具 ID，调用方选择允许的 ID；开始 Run 后按普通审批契约处理。

配置管理工具仍可保存记录，但这些记录不能自动成为进程启动授权。SDK 直接使用 `connectMcpServer` 或 `McpConnectionManager`，传入可信配置。

## Hook

| 事件 | 支持动作 | 失败语义 |
| --- | --- | --- |
| before_request | append_system、append_user、record | 阻止下一模型请求 |
| after_response | record | 记录 hook_error |
| pre_tool_use | deny_tool、record | 阻止工具执行 |
| post_tool_use | record | 记录 hook_error，不抹掉已有结果 |
| worktree_create / worktree_remove | record | 记录 hook_error |

- 单事件最多 99 个 Hook；达到存储查询上限时显式失败，避免静默遗漏控制 Hook。
- 单 Hook 文本 4 KiB，单事件指导文本总量 64 KiB；存储读取 5 秒超时并接受取消。
- matcher 支持精确名称或末尾 `*`；不解释 shell 或脚本。run_command 为保留记录类型，新配置和运行调度均拒绝执行。
- 按 created_at、hook_id 排序；在审批恢复时重新读取，权限可收紧、不能通过 Hook 放宽。
- hook_executed/hook_error 进入运行事件存储。历史 run_count/last_run_at 不作为执行事实依据。

## Host / App

- 工具开始事件在 handler 执行前交付；完成结果和错误随后交付。Web 工具错误不再投影为成功。
- Web 停止按钮中断当前请求，Host 将断连传播到模型/工具 AbortSignal。客户端请求结束不代表后台已取消，最终状态以存储事件为准。
- Terminal 只允许一个前台回合，运行时仍可读取取消/退出；真实模型流可被取消。
- 审批只授权当前调用，Web 移除误导性的整次任务授权按钮；同一次审批的重复/过期响应仍拒绝。
- TaskService 的当前进程执行向下传递取消信号并避免同实例重复启动；这不是跨进程任务租约或崩溃恢复。

## 证据

- Bun 1.4.4，`bun run check`：292 pass / 0 fail；core/host/terminal 类型检查、Web production build、终端四项 smoke 全部通过。
- MCP 使用真实 stdio 子进程和本地 HTTP fixture：初始化、分页、资源/prompt/工具读取、错误结果、取消通知、DELETE 终止和显式重连。
- Hook 测试包含审批期间新增拒绝规则、指导注入、稳定顺序、跨租户隔离、非法命令动作以及取消挂起的存储读取。
- Host 测试通过真实 HTTP SSE 断连和独立 Terminal 子进程验证取消落库。
- 额外使用 Playwright Chromium 操作实际 Web 页面：批准文件写入、拒绝、停止慢模型流、供应商 503；确认取消状态落库，无 pageerror。浏览器模型仍为本地 fixture。

浏览器验收入口（先运行 `bun run build-web`）：

```sh
bun run packages/host/test/fixtures/kernelBrowserHost.ts
```

访问 `http://127.0.0.1:5189/ui/`。输入 `approval` 验证审批；输入 `slow` 后停止验证取消；输入 `fail` 验证错误。fixture 使用临时工作空间和本地模型，不接入用户凭据；SIGTERM/SIGINT 退出时清理临时数据。

## 明确的剩余边界

本轮没有真实商业模型、远端第三方 MCP、Windows/Linux 原生进程树或 clean-host 发布证据。任意脚本 Hook、旧式 SSE/WS MCP、自动副作用重放均未开启。JSON store 仍为单进程基线，完整任务恢复归 B2。界面沿用现有设计，本轮不重构宣传页或产品信息架构。
