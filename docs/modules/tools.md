# Tools 模块说明

`agents.kernel.capabilities.tools` 是模型可见能力的注册和执行边界。

## 工具设计原则

- 工具名表达语义，不表达底层实现。
- 工具参数结构化。
- 工具结果结构化。
- 高风险工具必须受 permission policy 和 sandbox policy 双重约束。
- 能用 native tool 解决，就不要默认让模型写 shell。

## 当前内置工具

| 工具 | 说明 |
|---|---|
| `filesystem.read` | 读 workspace 文本文件 |
| `filesystem.list` | 列 workspace 目录 |
| `filesystem.write` | 写 workspace 文本文件 |
| `filesystem.delete` | 删除 workspace 文件或递归删除目录 |
| `filesystem.move` | 移动或重命名 workspace 文件/目录 |
| `notebook.edit` | 按 cell 编辑 Jupyter notebook，并复用读前写入安全 |
| `patch.apply` | 基于精确文本匹配做结构化 edit/create，并返回 unified diff |
| `search.grep` | 正则搜索 workspace 文本 |
| `search.glob` | 用 glob pattern 查找 workspace 文件 |
| `structured.output` | SDK/非交互场景返回结构化 JSON 输出，可由 `structured_output_schema` 收紧 schema |
| `skill.invoke` | 调用本地 skill；inline skill 通过 tool result 注入指令，fork skill 复用 child-session 边界执行 |
| `web.search` | 通过 control-plane Tavily provider 搜索网页并返回 sources |
| `web.extract` | 对指定 URL 做正文抽取，适合 search 后二次取证 |
| `web.map` | 发现站点 URL 结构，高风险且不默认启用 |
| `worktree.enter` | 创建或恢复隔离 git worktree，并把 session workspace 切换过去 |
| `worktree.exit` | 退出当前 worktree；可保留，或在安全检查后删除 worktree/branch |
| `git.status` | 查看 Git 状态 |
| `git.diff` | 查看 Git diff |
| `git.add` | stage workspace 改动 |
| `git.commit` | 创建 Git commit |
| `git.log` | 查看 Git history |
| `git.show` | 查看 Git revision / patch |
| `test.discover` | 根据项目标记推断测试命令，不执行 |
| `test.run` | 运行测试命令 |
| `shell.run` | 运行 shell 命令；支持 `run_in_background` 后台执行 |
| `shell.output` | 读取后台 shell 命令状态和输出 |
| `shell.backgrounds` | 列出当前 session 启动的后台 shell 命令 |
| `shell.kill` | 停止后台 shell 命令 |
| `sleep.wait` | 不占用 shell 进程的可中断等待工具 |
| `browser.open` | 在 sandbox 内抓取 HTTP(S) 页面，默认写入 run artifact store |
| `browser.download` | 在 sandbox 内下载 HTTP(S) 资源；无 path 时写 artifact store，有 path 时写 workspace |

同时注册第一层 `src-origin` tool-name aliases：`Read`、`Write`、`Edit`、`Bash`、`Glob`、`Grep`、`TodoWrite`、`NotebookEdit`、`Sleep`、`WebSearch`、`WebFetch`、`ListMcpResourcesTool`、`ReadMcpResourceTool`、`TaskOutput`、`AgentOutputTool`、`BashOutputTool`、`TaskStop`、`KillShell`、`TaskCreate`、`TaskList`、`TaskGet`、`TaskUpdate`、`CronCreate`、`CronList`、`CronDelete`、`ToolSearch`、`EnterPlanMode`、`ExitPlanMode`、`Agent`、`Task`、`SendMessage`、`TeamCreate`、`TeamDelete`、`StructuredOutput`、`Skill`、`Config`、`AskUserQuestion`、`SendUserMessage`、`Brief`、`EnterWorktree`、`ExitWorktree`。这些 alias 暴露 `src-origin` 风格参数名，例如 `Read.file_path`、`Write.file_path`、`Edit.old_string/new_string`、`WebSearch.allowed_domains`、`WebFetch.prompt`、`TaskUpdate.taskId`、`CronCreate.cron`、`Agent.subagent_type`、`SendMessage.to`、`TeamCreate.team_name`、`Skill.skill/args`、`Config.setting/value`、`AskUserQuestion.questions/answers`、`SendUserMessage.message/attachments/status`、`EnterWorktree.name`、`ExitWorktree.action/discard_changes`，内部仍路由到解耦后的 Python-native canonical tools。

## Tool Impact

approval 事件和 audit 记录会附带 `impact`：

- `risk`：low/medium/high/critical。
- `paths`：将读取或修改的 workspace 路径。
- `commands`：将执行的命令。
- `domains`：将访问的网络域名。
- `writes_files` / `requires_network`：UI 和策略层可直接使用的布尔标记。
- `external_disclosure`：是否把 query/URL 发给外部 provider。
- `cost_estimate`：例如 Tavily credit 估算。
- `diff_preview`：`patch.apply`、`filesystem.write` 等写入类工具的预览。

## Tool Contract

`ToolRegistry` 支持两种注册方式：

- `register(...)`：兼容旧调用点，适合简单内置工具和测试。
- `register_definition(ToolDefinition(...))`：面向 SDK 化工具契约，显式声明 schema、只读/破坏性、状态写入、并发安全、中断行为、结果长度限制和 metadata。

核心 coding tools 已经开始使用显式契约注册：

- 文件、patch、search 工具声明 workspace/edit activity 和路径参数。
- git、test、shell 工具声明 git/terminal activity，并把非并发安全的命令类工具串行化。
- web/browser 工具声明 web/browser activity、网络需求和 artifact/path 目标。
- `src-origin` aliases 通过同一套 `ToolDefinition` 注册，metadata 带 `alias_of` 和 `src_origin_tool`，因此 SDK/UI 可以显示原始工具名，同时权限和执行复用 canonical tool 行为。
- `config.manage` 提供 `src-origin` `Config` 的第一层 parity：输入为 `setting` 加可选 `value`，省略 `value` 时读取配置并自动允许，带 `value` 时写入 session-scoped config override 并要求 approval。当前覆盖了 `supportedSettings.ts` 中的 theme/editor/notification/model/permission/language/teammate/voice/remote/notification keys；`model` 会更新当前 `AgentSpec` 和可用 runtime config，`permissions.defaultMode` 会映射到本地 permission policy 并持久化到 session state metadata。
- `user.ask` 提供 `src-origin` `AskUserQuestion` 的第一层 core parity：工具 schema 支持 1-4 个问题、每题 2-4 个选项、`multiSelect`、`preview`、`answers` 和 `annotations`；权限策略会把它作为 user-interaction pause，而不是普通 read-only tool 直接执行。Runtime resume 支持 `tool_inputs`，可以在 approval resume 时把用户选择的 `answers` 合并回 pending tool call，再执行工具并把答案作为 tool result 送回模型。
- `user.message` 提供 `src-origin` BriefTool / `SendUserMessage` 的第一层 core parity：`SendUserMessage` 和 legacy `Brief` 都映射到同一 canonical tool，输入包含 `message`、`attachments` 和 `status=normal|proactive`。attachments 会解析为 workspace 内文件，返回 `path`、`size`、`isImage` 和 `sentAt`，model-visible 结果对齐为 `Message delivered to user.` 加附件数量说明；team 内消息仍由 `SendMessage`/`team.send` 独立负责。
- `worktree.enter` / `worktree.exit` 提供 `src-origin` `EnterWorktree` / `ExitWorktree` 的 git-backed core parity：进入时在 repo 内 `.agents/worktrees/<slug>` 创建或恢复 `worktree-<slug>` 分支，并重绑当前 `WorkspaceContext` 与 sandbox；新建 worktree 会做第一层后处理，包括把 `.agents/worktrees/` 加入 local git exclude、复制 `.worktreeinclude` 命中的 ignored files、复制被 git ignore 的 `.env` / `config/local.toml` / `.agents/settings.local.json`、配置 `core.hooksPath`、以及按 `AgentSpec.metadata.worktree.sparse_paths` / `symlink_directories` 或 settings 中的 `WORKTREE_SPARSE_PATHS` / `WORKTREE_SYMLINK_DIRECTORIES` 执行 sparse checkout 和目录 symlink；退出时 `keep` 只恢复原 workspace，`remove` 会先检查未提交文件和新增提交，除非显式 `discard_changes=true` 否则拒绝删除。当前不包含 `src-origin` 的 tmux session、hook-based VCS adapter、PR fetch/resume 和 attribution hook 后处理。
- MCP server tools 现在按 `src-origin` 动态命名规则注册 canonical 名称：`mcp__<normalized_server>__<normalized_tool>`，其中非字母数字/`_`/`-` 字符会归一为 `_`；旧的 `mcp_<server>_<tool>` 名称仍作为兼容 alias 注册并带 `alias_of` metadata。bridge `/mcp reload` 只自动启用 canonical 名称，避免同一个远端工具重复出现在 active tools 中。MCP 配置和 provider 也有第一层 HTTP/SSE/auth-required 契约：`mcp.configure` 可保存 `transport=http|sse`、`url` 和 headers；loader 会用 Python MCP SDK 的 Streamable HTTP / SSE transport 建立 client；当 server 标记为需要认证或 list-tools 抛出 auth-required 错误时，会暴露 `mcp__<server>__authenticate` pseudo-tool，返回 `auth_url` / `unsupported` / `error` 结构化结果。当前还没有真实 OAuth callback、token cache 和认证完成后的 reconnect/swap。

`ToolRegistry.describe_call(name, arguments)` 会基于同一份契约返回 activity、target、paths 和 metadata。权限、trace、operation stage 和未来 SDK event projector 应使用这个入口，而不是重新解析工具参数。

runtime 已经把这个契约写入工具事件：

- `tool_start`、`tool_result` 带 `payload.contract`。
- `tool_approval_required`、`tool_approval_decision` 带同一份 `payload.contract`。
- SDK `tool_progress` 会投影出 `activity`、`target`、`paths` 和 `metadata` 字段。
- server trace 的 `operation_frames` 会从 runtime contract 生成基础 operation frame，再叠加 sandbox trace 的文件、artifact 和 snapshot evidence。

执行前会基于工具的 JSON schema 做基础输入校验：

- 校验 `required`。
- 校验常见类型：`string`、`integer`、`number`、`boolean`、`object`、`array`、`null`。
- 支持 `enum`、嵌套 object/array 和 `additionalProperties: false`。
- 校验失败会返回 model-visible error result，不调用工具 handler。

文件写入工具开始执行 `src-origin` 风格的会话内写入安全：

- `filesystem.read` 完整读取文件后，会在 `ToolRuntimeContext.file_read_state` 记录该文件内容。
- `filesystem.read` 现在支持 `offset`/`limit` 行范围读取，并返回 `type=text`、`file.filePath`、`file.content`、`file.numLines`、`file.startLine`、`file.totalLines`，同时保留原有顶层 `content`、`startLine`、`numLines`、`totalLines`、`isPartialView`；model-visible 输出使用 `cat -n` 风格行号。完整文本读取超过默认 256KB `max_bytes` 时会返回 `src-origin` 风格超限错误并提示改用 `offset`/`limit`，带 `limit` 的范围读取不受完整文件大小限制。只有完整读取会满足后续 `filesystem.write`/`patch.apply` 的预读安全要求，局部读取不会被误当作全文件已读。
- `filesystem.read` 读取缺失文件时会返回 `src-origin` 风格 cwd note，并在同目录存在同 basename、不同扩展名文件时用文件名提示 `Did you mean ...?`；读取目录时返回 `EISDIR: illegal operation on a directory, read ...`；`/dev/random`、`/dev/zero`、stdio fd 别名等会阻塞或无限输出的设备路径会在 sandbox 解析前返回 `Cannot read ... this device file would block...`。
- `filesystem.read` 对同一文件同一完整范围的重复读取会在 mtime 未变化时返回 `file_unchanged` stub，避免把同一份内容重复塞进模型上下文；该 stub 保留之前的完整读状态，后续安全写入仍可正常校验。
- `filesystem.read` 读取 managed auto memory、team memory、agent memory、session memory 路径下超过 1 天的 markdown 记忆文件时，会在 model-visible 文本前加 `src-origin` 风格 freshness reminder，并在 `memoryFreshness` 里标注 `memoryKind` / `scope`；普通 markdown、`CLAUDE.md` / `.claude/rules` 指令文件和今天/昨天的记忆文件不会加噪音。
- `filesystem.read` 现在有第一层 `src-origin` FileRead 多类型输出：PNG/JPEG/GIF/WebP 会返回 `type=image`，PDF 会返回 `type=pdf`，notebook 会返回 `type=notebook`；这些 payload 使用 `file.filePath`、`file.base64`、`file.type`、`file.originalSize`、`file.dimensions` 或 `file.cells` 等 `src-origin` 字段。model-visible 图片/PDF 文本只给摘要，notebook 会输出 cells JSON；空 image 会返回 `Image file is empty...`，未知非空 image magic bytes 默认按 PNG 投递，PNG/GIF/JPEG/VP8X WebP 会附带原始/显示尺寸；macOS screenshot `.png` 路径如果只差 AM/PM 前普通空格与 U+202F 窄不换行空格，会在 ENOENT 后自动尝试另一个变体；普通文本分支遇到二进制文件时会返回 `src-origin` 风格 `This tool cannot read binary files... Please use appropriate tools...` 错误，常见二进制扩展会在 I/O 前按路径直接拒绝，缺失 `.zip` 也不会误报成 missing file。PDF `pages` 支持 `1` / `1-5` 这类 1-indexed range、最多 20 页，并在本机有 `pdftoppm` 时返回 `type=parts`、`file.count` 和包含 page JPEG 的 `file.outputDir`；缺少 poppler 时会给出显式依赖错误。
- `filesystem.write` 覆盖已有文件前要求该文件已被完整读取；如果读后文件内容发生变化，会返回 stale-write error，要求重新读取。写入内容也对齐 `src-origin` FileWrite：非 Markdown 文件按行去掉尾随空白，`.md` / `.mdx` 保留 Markdown 硬换行空格，并把内容视为整文件替换，按输入行尾写入。成功结果会返回 `type=create|update`、`filePath`、`content`、`originalFile` 和 `structuredPatch`，供 SDK rewind、diff UI 和 trace 消费。
- `notebook.edit` 提供第一层 `src-origin` `NotebookEdit` parity：按 `cell_id` 或 `cell-N` index 对 `.ipynb` cell 做 `replace`、`insert`、`delete`，要求先通过 `filesystem.read` 完整读取 notebook，拒绝 stale 外部修改，替换 code cell 时清空 `outputs` 并重置 `execution_count`，写回后刷新读状态并返回 `original_file` / `updated_file` 供 SDK/UI 使用。
- `patch.apply` 对已有文件做 edit/overwrite 前使用同一份读状态；新文件 create 不要求预读。
- `patch.apply` 的 edit 校验进一步贴近 `src-origin` FileEdit：`old_text == new_text` 会直接拒绝；多处命中但未设置 `replace_all=true` 会要求提供更具体上下文；直引号 `old_text` 可匹配文件中的弯引号，替换时会保持文件原有弯引号风格；非 Markdown 文件的 `new_text` 会按行去掉尾随空白，`.md` / `.mdx` 会保留 Markdown 硬换行空格；同一文件的后续 edit 如果会命中前一个 edit 刚插入的 `new_text`，会在写入前拒绝；`<fnr>` / `<r>` 等 `src-origin` 脱敏占位符可匹配真实标签并同步反解到 `new_text`；当 `new_text=""` 且匹配文本后紧跟换行时，会按 FileEdit 语义删除整行换行，避免留下空白行；成功结果会额外返回 `editSummary` 和 `structuredPatches`，单 edit 时还返回 `filePath`、`oldString`、`newString`、`originalFile`、`replaceAll` 和 `structuredPatch`。
- 工具成功写入后会刷新该文件的读状态，避免同一轮连续安全编辑被误判为 stale。
- `patch.apply` / `notebook.edit` 这类编辑型工具覆盖已有 CRLF 文件时会保持 CRLF 行尾；`filesystem.write` 则按 FileWrite 语义使用输入内容的行尾。
- sandbox text reads 会拒绝常见 binary 扩展、NUL 字节和高控制字符比例文件；`filesystem.read`、`filesystem.write` 覆盖已有文件、`patch.apply` 和 `search.grep` 都复用该 binary guard。
- sandbox text reads 会返回 `encoding` 和 `line_endings` 元数据；已有文件覆盖和 patch 编辑会沿用完整读取时记录的编码，目前覆盖 UTF-8、UTF-8 BOM 和 UTF-16LE/BOM 文本文件。

并发工具批次会执行基础 interrupt 行为：

- `cancels_siblings_on_error=true` 的工具失败时，会取消同批未完成的并发 sibling 工具；当前 `shell.run` 显式启用，普通读/搜索类工具失败不会取消同批工具。
- 被取消的 sibling 会得到 synthetic `tool_execution_canceled` tool result，保证下一轮模型不会缺 tool result。
- `interrupt_behavior` 默认是 `block`，与 `src-origin` 一致；只有显式 `interrupt_behavior="cancel"` 的工具会被“提交新消息导致的 interrupt”取消。
- `task.cancel("interrupt")` 会等待 `block` 工具完成并继续原 turn；遇到显式 `cancel` 工具时生成 synthetic `tool_execution_canceled` result，并标记 `raw.cancel_reason="user_interrupted"`。
- 普通 active run cancel 仍然是强制取消，会为当前和未执行的 pending tool call 生成 synthetic `tool_execution_canceled` result。
- terminal 会从 runtime event 的 `payload.contract.metadata.interrupt_behavior` 维护 active tool interruptible state；普通输入在所有 active tools 都可取消时会排队并发送 `cancel(reason="interrupt")`，否则只排队等待当前 turn。
- runtime 识别用户 interrupt result 后会返回 `AgentResult.status="canceled"`，streaming 模式会发出 `done.status="canceled"`，不会再继续下一轮模型请求。
- 顺序工具批次会在当前工具被取消后为剩余工具补齐 synthetic result；并发批次会取消所有 pending task 并补齐 synthetic result，保持 model-visible tool result 数量和 tool call 数量一致。

后台 shell 命令现在有第一层 `src-origin` 风格生命周期：

- `shell.run` 接受 `run_in_background=true`，立即返回 `task_id`、`status` 和 `.agents/task-output/<task_id>.log` 输出文件路径。
- local 和 Docker sandbox 都通过 `SandboxBackgroundCommand` 句柄统一启动、追踪、停止后台命令。
- `shell.output` 可非阻塞读取当前输出，也可 `block=true` 等待完成；返回 `retrieval_status`、task 状态、exit code、输出字节和截断信息。
- `shell.backgrounds` 列出当前 session 的后台 shell 命令。
- `shell.kill` 停止后台 shell 命令，并将状态投影为 `killed`。

`shell.run` 同时接受现有的 `timeout_seconds` 和 `src-origin` BashTool 风格的 `timeout` 毫秒字段；前台和后台命令都会在 raw payload 中返回 `description`、`background`、`timeout_seconds`、`timeout_ms`、`interrupted`、`isImage` 和 `dangerouslyDisableSandbox`，方便 SDK/UI 用同一套契约投影命令生命周期。后台启动结果还会返回 `backgroundTaskId`、`backgroundedByUser=false`、`assistantAutoBackgrounded=false` 这些 `src-origin` output schema 字段；当前 runtime 没有无沙箱执行策略，因此 `dangerouslyDisableSandbox=true` 会被显式拒绝，而不是静默忽略。

`sleep.wait` 提供 `src-origin` Sleep 工具的基础能力：模型需要等待时可使用专用 wait tool，而不是用 `shell.run` 执行 `sleep` 占住 shell 进程。该工具是只读、并发安全、可被 interrupt 取消的低风险工具。

任务工具的 alias 层覆盖 `TaskCreate`、`TaskList`、`TaskGet`、`TaskUpdate`、`TaskOutput`、`TaskStop` 以及旧名 `AgentOutputTool` / `BashOutputTool` / `KillShell`。其中 `task.update` 已扩展为可更新 title/input/status/metadata，`TaskUpdate.subject`、`description`、`activeForm`、`owner` 和依赖数组会通过 adapter 映射到 Python-native task store。

Agent/team alias 层覆盖 `Agent`、旧名 `Task`、`SendMessage`、`TeamCreate` 和 `TeamDelete`。`Agent` / `Task` 复用 `agent.run` 的 child-session 边界；`TeamCreate` 会创建带 `team-lead` 成员的 Python-native team；`SendMessage` 路由到 `team.send`；`TeamDelete` 通过 canonical `team.delete` 清理 team record 和 queued messages。

为贴近 `src-origin` 的 Bash/Sleep 分工，foreground `shell.run` 会拒绝 `sleep N` 这类 2 秒及以上的 standalone/leading sleep 命令，并提示改用 `sleep.wait` 或 `run_in_background=true`。短暂的 `sleep 1`、小数秒 sleep、pipeline 内 sleep 和显式后台 shell 命令不受这个 guard 影响。

同步命令结果会额外返回 `failed`、`no_output_expected` / `noOutputExpected` 和 `return_code_interpretation` / `returnCodeInterpretation`，让模型和 UI 能区分“命令成功且本来就没有输出”和“命令失败/超时但输出为空”。非零退出会先按 `src-origin` BashTool 的命令语义解释：`grep`/`rg` exit 1 是 `No matches found`，`diff` exit 1 是 `Files differ`，`find` exit 1 是部分目录不可访问，`test`/`[` exit 1 是条件为 false；只有真正错误的非零退出和超时会通过 `ToolExecutionError` 返回 model-visible error result，同时保留结构化 raw payload，包括 `command`、`exit_code`、`stdout`、`stderr` 和失败解释。raw payload 还包含 `command_classification` / `commandClassification`，对齐 `src-origin` 的 Bash search/read/list 折叠分类。

权限和 Hook matcher 已开始兼容 `src-origin` 的 Bash 规则格式：

- `Bash` / `Bash(*)` 是 `shell.run` 的工具级规则。
- `Bash(git *)` 会匹配 `git`、`git status` 和 `FOO=bar git status`，但不会匹配 `echo git status`。
- `Bash(git:*)` 保留 legacy prefix 语义，匹配 bare `git` 和 `git ...`。
- 复合命令按 subcommand 匹配，例如 `npm test && git status` 会命中 `Bash(git *)`。
- pre/post tool hooks 对复杂 shell 解析 fail-safe：无法可靠解析时会运行匹配到 `Bash(...)` 的 hook，避免安全 hook 被绕过。
- `Read(src/**)`、`Write(secrets/**)`、`Edit(src/**)`、`NotebookEdit(notebooks/**)` 兼容 `src-origin` 的路径 wildcard 规则，分别映射到 `filesystem.read`、`filesystem.write`、`patch.apply`、`notebook.edit`。
- `Grep(TODO*)` / `Glob(*.py)` 使用工具的搜索 pattern 做 wildcard 匹配；`Glob` 已映射到 `search.glob`。
- `search.grep` 的 model-visible result 开始对齐 `src-origin` Grep：默认输出 `Found N files` 加文件列表，`output_mode=content` 输出 `path:line:match`，`output_mode=count` 输出每文件计数和汇总；`glob` 参数可按文件名过滤搜索范围，支持空格/逗号拆分、`*.{py,tsx}` 这类 brace pattern 和 `!*.test.py` 排除规则；`type` 提供常见文件类型过滤，`multiline=true` 支持跨行正则；`head_limit`、`offset`、`context`、`-A`、`-B`、`-C`、`-n` 和 `-i` 覆盖 GrepTool 的第一层分页、上下文、行号和大小写控制。
- `search.glob` 的 model-visible result 和 `src-origin` 对齐为逐行文件名；无结果时返回 `No files found`，截断时追加明确提示。

这只是 `src-origin` parity 的第一层工具契约。后续还需要补齐完整 strict schema、权限上下文感知描述、活动摘要、后台工具、更广泛的编码矩阵、专用媒体读取和更精细的结果预算。

## Web Search

内置 web 搜索不走 MCP。`web.search`、`web.extract`、`web.map` 使用 `agents.kernel.capabilities.web` 下的 provider 抽象，当前实现为 Tavily REST provider。

边界：

- Tavily API key 留在 control plane。
- 工具结果统一成 `sources`、`usage`、`request_id`，便于 citation、trace 和 audit。
- 默认不返回 raw content；需要时走 `web.extract`。
- `web.map` 用于站点 URL 发现，不替代 crawl。
- `browser.open/download` 是 sandbox 网络工具，负责落文件；`web.search/extract/map` 是 control-plane 信息检索工具。

## 为什么要有 native tools

只给 `shell.run` 会让模型做所有决策，系统很难知道它要干什么。native tools 可以带来：

- 更好的权限审批。
- 更好的审计记录。
- 更稳定的提示词行为。
- 更容易做 UI 展示。
- 更容易做 protocol-neutral replay。

## 后续重点

- 真实浏览器 runtime：`browser.click`、`browser.type`、`browser.screenshot`。
- package/install 类工具。
- 更完整的 `src-origin` 工具生命周期 parity：strict schema、路径 matcher、权限上下文描述、活动摘要、更广泛的编码矩阵、PDF page image 投递、专用媒体读取和后台执行。
