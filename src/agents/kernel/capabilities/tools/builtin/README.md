# Builtin Tool Boundaries

This package separates registry wiring from tool behavior.

## Registration And Wiring

These files should only bind schemas, aliases, metadata, and handlers into `ToolRegistry`:

- `registration.py`
- `automation_registration.py`
- `collaboration_registration.py`
- `development_registration.py`
- `execution_registration.py`
- `extension_registration.py`
- `interaction_registration.py`
- `registration_helpers.py`
- `runtime_registration.py`
- `state_registration.py`
- `web_registration.py`
- `workspace_registration.py`
- `tool_names.py`
- `task_schemas.py`
- `src_origin_aliases.py`
- `src_origin_agent_aliases.py`
- `src_origin_core_aliases.py`
- `src_origin_discovery_aliases.py`
- `src_origin_plan_aliases.py`
- `src_origin_schedule_aliases.py`
- `src_origin_session_aliases.py`
- `src_origin_task_aliases.py`
- `mcp/registration.py`

Registration files should stay thin. They should not own business behavior, persistent state transitions, protocol clients, or large helper classes. `src_origin_*_aliases.py` files are compatibility wiring for existing canonical tools; the behavior stays in the implementation modules below.

## Core Implementation

Domain behavior belongs in focused implementation modules, for example:

- Files and edits: `filesystem.py`, `patch.py`, `notebook.py`, `file_safety.py`, `file_diff.py`, `read_paths.py`, `read_errors.py`
- Execution and lifecycle: `shell.py`, `shell_lifecycle.py`, `shell_notifications.py`, `shell_prompt_stall.py`, `tests.py`, `git.py`, `sleep.py`
- Worktree domain: `worktree.py` owns public tool orchestration; `worktree_naming.py`, `worktree_git.py`, `worktree_setup.py`, and `worktree_state.py` own naming, git operations, post-create setup, and session/workspace state.
- Product capabilities: `tasks.py`, `task_src_origin.py`, `schedules.py`, `agents.py`, `teams.py`, `commands.py`, `prompts.py`, `workflows.py`, `user_interaction.py`
- Extension surfaces: `extensions.py`, `plugins.py`, `skill_discovery.py`, `skill_invocation.py`, `hooks.py`, `permissions.py`, `config.py`
- Search, web, browser, and LSP: `search.py`, `web.py`, `browser.py`, `lsp.py`
- MCP domain tools: `mcp/management.py`, `mcp/prompts.py`, `mcp/resources.py`, `mcp/ide.py`

Implementation modules should expose behavior that registration files can wire. They should not add top-level `register_*` functions; architecture tests enforce that boundary.
