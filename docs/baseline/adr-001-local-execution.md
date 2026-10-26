# ADR 001：本地执行与平台沙箱分离

日期：2026-10-26。状态：当前本地执行接口已实现；隔离后端按用户决定延期。

## 决定

- 个人设备默认不依赖 Docker。保留 Windows MXC、macOS 原生、Linux 原生、可选容器后端名称与 CommandExecutor 接口。未实现的后端不注册、不假报可用。
- `ports/commandExecutor.ts` 定义命令请求、结果、取消、后端能力和可信 ExecutionPolicy。`execution/localExecutor.ts` 提供宿主执行。策略只从服务端 RuntimeOptions 注入，不从模型参数提升权限。
- `mode: isolated` 包含文件、网络、环境策略；当前 LocalExecutor 拒绝此模式。通用工具入口同样拒绝 isolated，防止文件/Git/MCP 等仍在宿主执行时仅替换 Shell 就误报全工具隔离。后续必须同时完成 executor 和各工具执行路由。
- Shell 前台和后台统一经过 CommandExecutor。Runtime 的 AbortSignal 传递给命令；超时/取消先发送进程组 TERM，200ms 后 KILL 并收敛输出管道。
- 当前 POSIX 进程组不约束 setsid 等主动逃逸，不是安全沙箱。Windows 本地命令后端明确报不支持，待独立 Windows 进程监督实现与实机验证，不用未验证实现冒充支持。

## 当前界限

命令默认 30 秒，上限 120 秒；stdout/stderr 各保留 128 KiB，继续消费后续数据但明确标记截断和原始字节数。后台记录最多 128 条，优先淘汰已结束记录；全部活跃时拒绝新增。后台查询最大等待 120 秒。后台输出是内存记录，不再返回未实际生成的 output_path。

通用工具输入和返回各限制 256 KiB。返回超限时提供有效 JSON 截断摘要，不把已成功执行的副作用标成可重试失败。不代表 handler 内存使用已有全局界限：文件读取/第三方响应等仍需逐工具流式界限。

LocalExecutor 继承宿主环境，能访问宿主文件和网络。平台沙箱、凭据隔离、网络代理/SSRF、MCP 生命周期与完整资源限制是明确未完成项。现有 Task cancel 尚未具备 B2 的持久取消、租约与副作用核对；本批只接通 Runtime/SDK 已有的 AbortSignal。

## 后续接入要求

后端报告实测能力；根据 OS/版本探测，不按产品名推断可用。所需限制不可落实则拒绝。所有执行路径都必须覆盖，不只 Shell。支持矩阵和故障测试更新后才能启用隔离后端。服务端容器镜像用于可复现交付，不等同于个人桌面隔离方案。
