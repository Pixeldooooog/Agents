# Builtin Tool Boundaries

This package separates registry wiring from tool behavior.

The package `__init__.py` intentionally exposes only `register_builtin_tools`.
Callers that need concrete schemas or handlers should import the responsible
domain module directly instead of relying on a broad package-level export list.

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
- `src_origin/aliases.py`
- `src_origin/agent_aliases.py`
- `src_origin/core_aliases.py`
- `src_origin/discovery_aliases.py`
- `src_origin/plan_aliases.py`
- `src_origin/schedule_aliases.py`
- `src_origin/session_aliases.py`
- `src_origin/task_aliases.py`
- `mcp/registration.py`

Registration files should stay thin. They should not own business behavior, persistent state transitions, protocol clients, or large helper classes. `src_origin/` files are compatibility wiring for existing canonical tools; the behavior stays in the implementation modules below.

## Core Implementation

Domain behavior belongs in focused implementation modules, for example:

- Filesystem domain: `filesystem.py` owns public schemas plus thin `filesystem.list/write/delete/move` wrappers; `filesystem_read.py`, `filesystem_media.py`, `filesystem_limits.py`, `filesystem_memory.py`, and `filesystem_results.py` own read orchestration, image/PDF/notebook delivery, read budgets, memory freshness, and result formatting; `file_safety.py`, `file_diff.py`, `read_paths.py`, and `read_errors.py` provide shared file safety/error helpers.
- Patch/Edit domain: `patch.py` owns public `patch.apply` / `Edit` / `MultiEdit` orchestration; `patch_planner.py`, `patch_text.py`, `patch_payload.py`, and `patch_types.py` own planning, text matching, result shaping, and small data contracts.
- Execution and lifecycle: `shell.py`, `shell_lifecycle.py`, `shell_notifications.py`, `shell_prompt_stall.py`, `tests.py`, `git.py`, `sleep.py`
- Worktree domain: `worktree.py` owns public tool orchestration; `worktree_naming.py`, `worktree_git.py`, `worktree_setup.py`, `worktree_state.py`, `worktree_tmux.py`, `worktree_hooks.py`, and `worktree_hook_commands.py` own naming, git operations, post-create setup, session/workspace state, tmux lifecycle, hook-based adapter orchestration, and hook command discovery/execution.
- Product capabilities: `tasks.py`, `task_src_origin.py`, `schedules.py`, `agents.py`, `teams.py`, `commands.py`, `prompts.py`, `workflows.py`, `user_interaction.py`
- Extension surfaces: `extensions.py`, `plugins.py`, `skill_discovery.py`, `skill_invocation.py`, `hooks.py`, `permissions.py`, `config.py`
- Search, web, browser, and LSP: `search.py`, `web.py`, `browser.py`, `lsp.py`
- MCP domain tools: `mcp/management.py` owns public management tool handlers; `mcp/settings.py`, `mcp/store.py`, and `mcp/runtime.py` own settings/header parsing, config/auth store access, and provider/registry runtime changes; `mcp/prompts.py`, `mcp/resources.py`, and `mcp/ide.py` own their focused tool domains.
- Src-origin compatibility: `src_origin/agent_resolution.py` owns Agent selection flow; `agent_profile_lookup.py` owns profile discovery; `agent_profile_spec.py` applies profile specs; `agent_definition_options.py`, `agent_permission_mode.py`, `agent_skills.py`, `agent_initial_prompt.py`, `agent_memory.py`, `agent_context_options.py`, `agent_system_reminder.py`, `agent_tool_rules.py`, and `agent_mcp_requirements.py` own definition metadata, permission mode mapping, skill preload metadata, initial prompt handling, memory scope mapping, context inclusion options, critical reminder metadata, tool allow/deny semantics, and MCP prerequisites; `agent_metadata.py` contains shared metadata parsing.

Implementation modules should expose behavior that registration files can wire. They should not add top-level `register_*` functions; architecture tests enforce that boundary.
