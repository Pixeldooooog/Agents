from __future__ import annotations

SANDBOX_LEASE_COLUMNS = {
    "run_id": "TEXT NOT NULL DEFAULT ''",
    "task_id": "TEXT NOT NULL DEFAULT ''",
}


SANDBOX_EVENT_COLUMNS = {
    "run_id": "TEXT NOT NULL DEFAULT ''",
    "task_id": "TEXT NOT NULL DEFAULT ''",
    "tool_call_id": "TEXT NOT NULL DEFAULT ''",
    "tool_name": "TEXT NOT NULL DEFAULT ''",
    "status": "TEXT NOT NULL DEFAULT ''",
    "duration_ms": "REAL NOT NULL DEFAULT 0",
}


APPROVAL_AUDIT_COLUMNS = {
    "impact_json": "TEXT NOT NULL DEFAULT '{}'",
    "decision": "TEXT NOT NULL DEFAULT 'allow_once'",
}


RUNTIME_CHECKPOINT_COLUMNS = {
    "tool_approval_scopes_json": "TEXT NOT NULL DEFAULT '{}'",
    "tool_approval_grants_json": "TEXT NOT NULL DEFAULT '{}'",
}


SESSION_STATE_COLUMNS = {
    "system_prompt_override": "TEXT NOT NULL DEFAULT ''",
    "system_prompt_overridden": "INTEGER NOT NULL DEFAULT 0",
    "permission_profile_override": "TEXT NOT NULL DEFAULT ''",
    "permission_mode_override": "TEXT NOT NULL DEFAULT ''",
    "permission_restrict_allowed_tools": "INTEGER NOT NULL DEFAULT 0",
    "permission_allowed_tools_override_json": "TEXT NOT NULL DEFAULT '[]'",
    "permission_denied_tools_override_json": "TEXT NOT NULL DEFAULT '[]'",
    "approval_required_tools_override_json": "TEXT NOT NULL DEFAULT '[]'",
    "permission_overridden": "INTEGER NOT NULL DEFAULT 0",
    "enabled_skills_json": "TEXT NOT NULL DEFAULT '[]'",
    "enabled_plugins_json": "TEXT NOT NULL DEFAULT '[]'",
    "skill_tools_json": "TEXT NOT NULL DEFAULT '{}'",
    "plugin_tools_json": "TEXT NOT NULL DEFAULT '{}'",
}


MCP_SERVER_COLUMNS = {
    "transport": "TEXT NOT NULL DEFAULT 'stdio'",
    "url": "TEXT NOT NULL DEFAULT ''",
    "headers_json": "TEXT NOT NULL DEFAULT '{}'",
    "auth_required": "INTEGER NOT NULL DEFAULT 0",
    "auth_url": "TEXT NOT NULL DEFAULT ''",
    "auth_status": "TEXT NOT NULL DEFAULT ''",
    "auth_message": "TEXT NOT NULL DEFAULT ''",
}


SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    roles_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY(tenant_id, user_id),
    FOREIGN KEY(tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS agent_profiles (
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    spec_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY(tenant_id, user_id, agent_id)
);

CREATE TABLE IF NOT EXISTS workspace_records (
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    metadata_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY(tenant_id, user_id, agent_id, workspace_id)
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL DEFAULT '',
    tenant_id TEXT NOT NULL DEFAULT '',
    user_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    metadata_json TEXT NOT NULL,
    spec_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runtime_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    event_index INTEGER NOT NULL,
    type TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL,
    raw_json TEXT,
    created_at REAL NOT NULL,
    UNIQUE(run_id, event_index),
    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS runtime_checkpoints (
    run_id TEXT PRIMARY KEY,
    step TEXT NOT NULL,
    iteration INTEGER NOT NULL,
    messages_json TEXT NOT NULL,
    tool_results_json TEXT NOT NULL,
    events_json TEXT NOT NULL,
    pending_tool_calls_json TEXT NOT NULL,
    tool_approvals_json TEXT NOT NULL,
    tool_approval_scopes_json TEXT NOT NULL DEFAULT '{}',
    tool_approval_grants_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS approval_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    approval_id TEXT NOT NULL,
    tool_name TEXT NOT NULL DEFAULT '',
    approved INTEGER NOT NULL,
    decision TEXT NOT NULL DEFAULT 'allow_once',
    reason TEXT NOT NULL DEFAULT '',
    tool_call_json TEXT NOT NULL,
    impact_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS trace_spans (
    span_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    parent_span_id TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at REAL NOT NULL,
    ended_at REAL,
    attributes_json TEXT NOT NULL,
    error TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_trace_spans_run_id_started_at
ON trace_spans(run_id, started_at);

CREATE TABLE IF NOT EXISTS memory_records (
    memory_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    agent_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    scope TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memory_records_context
ON memory_records(tenant_id, user_id, agent_id, workspace_id, created_at);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    input TEXT NOT NULL,
    agent_id TEXT NOT NULL DEFAULT '',
    tenant_id TEXT NOT NULL DEFAULT '',
    user_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    metadata_json TEXT NOT NULL,
    spec_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_scope
ON tasks(tenant_id, user_id, agent_id, created_at);

CREATE TABLE IF NOT EXISTS task_steps (
    step_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    step_index INTEGER NOT NULL,
    name TEXT NOT NULL,
    input TEXT NOT NULL DEFAULT '',
    run_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    output TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    metadata_json TEXT NOT NULL,
    UNIQUE(task_id, step_index),
    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_task_steps_task
ON task_steps(task_id, step_index);

CREATE TABLE IF NOT EXISTS task_attempts (
    attempt_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    run_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    started_at REAL NOT NULL,
    ended_at REAL,
    error TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id) ON DELETE CASCADE,
    FOREIGN KEY(step_id) REFERENCES task_steps(step_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_task_attempts_step
ON task_attempts(step_id, started_at);

CREATE TABLE IF NOT EXISTS task_queue_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT '',
    user_id TEXT NOT NULL DEFAULT '',
    agent_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_task_queue_items_scope
ON task_queue_items(tenant_id, user_id, agent_id, workspace_id, created_at);

CREATE TABLE IF NOT EXISTS schedules (
    schedule_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    input TEXT NOT NULL,
    schedule TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    agent_id TEXT NOT NULL DEFAULT '',
    tenant_id TEXT NOT NULL DEFAULT '',
    user_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    last_run_task_id TEXT NOT NULL DEFAULT '',
    last_run_at REAL NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_schedules_scope
ON schedules(tenant_id, user_id, agent_id, workspace_id, updated_at);

CREATE TABLE IF NOT EXISTS teams (
    team_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    agent_id TEXT NOT NULL DEFAULT '',
    tenant_id TEXT NOT NULL DEFAULT '',
    user_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    members_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY(tenant_id, user_id, agent_id, workspace_id, team_id)
);

CREATE INDEX IF NOT EXISTS idx_teams_scope
ON teams(tenant_id, user_id, agent_id, workspace_id, updated_at);

CREATE TABLE IF NOT EXISTS team_messages (
    message_id TEXT PRIMARY KEY,
    team_id TEXT NOT NULL,
    from_agent TEXT NOT NULL DEFAULT '',
    to_agent TEXT NOT NULL DEFAULT '',
    message_type TEXT NOT NULL DEFAULT 'message',
    message TEXT NOT NULL,
    read INTEGER NOT NULL DEFAULT 0,
    agent_id TEXT NOT NULL DEFAULT '',
    tenant_id TEXT NOT NULL DEFAULT '',
    user_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_team_messages_inbox
ON team_messages(tenant_id, user_id, agent_id, workspace_id, team_id, to_agent, read, created_at);

CREATE TABLE IF NOT EXISTS hooks (
    hook_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT '',
    user_id TEXT NOT NULL DEFAULT '',
    agent_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    event TEXT NOT NULL,
    name TEXT NOT NULL,
    action TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    metadata_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    last_run_at REAL NOT NULL DEFAULT 0,
    run_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_hooks_scope
ON hooks(tenant_id, user_id, agent_id, workspace_id, updated_at);

CREATE TABLE IF NOT EXISTS mcp_servers (
    name TEXT NOT NULL,
    command TEXT NOT NULL,
    transport TEXT NOT NULL DEFAULT 'stdio',
    url TEXT NOT NULL DEFAULT '',
    headers_json TEXT NOT NULL DEFAULT '{}',
    execution_mode TEXT NOT NULL DEFAULT 'trusted_control_plane',
    sandbox_profile TEXT NOT NULL DEFAULT '',
    auth_required INTEGER NOT NULL DEFAULT 0,
    auth_url TEXT NOT NULL DEFAULT '',
    auth_status TEXT NOT NULL DEFAULT '',
    auth_message TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1,
    agent_id TEXT NOT NULL DEFAULT '',
    tenant_id TEXT NOT NULL DEFAULT '',
    user_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY(tenant_id, user_id, agent_id, workspace_id, name)
);

CREATE INDEX IF NOT EXISTS idx_mcp_servers_scope
ON mcp_servers(tenant_id, user_id, agent_id, workspace_id, updated_at);

CREATE TABLE IF NOT EXISTS mcp_auth_tokens (
    name TEXT NOT NULL,
    access_token TEXT NOT NULL,
    token_type TEXT NOT NULL DEFAULT 'Bearer',
    refresh_token TEXT NOT NULL DEFAULT '',
    expires_at REAL NOT NULL DEFAULT 0,
    scopes_json TEXT NOT NULL DEFAULT '[]',
    tenant_id TEXT NOT NULL DEFAULT '',
    user_id TEXT NOT NULL DEFAULT '',
    agent_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY(tenant_id, user_id, agent_id, workspace_id, name)
);

CREATE INDEX IF NOT EXISTS idx_mcp_auth_tokens_scope
ON mcp_auth_tokens(tenant_id, user_id, agent_id, workspace_id, updated_at);

CREATE TABLE IF NOT EXISTS session_states (
    tenant_id TEXT NOT NULL DEFAULT '',
    user_id TEXT NOT NULL DEFAULT '',
    agent_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    todos_json TEXT NOT NULL DEFAULT '[]',
    plan_mode INTEGER NOT NULL DEFAULT 0,
    plan_text TEXT NOT NULL DEFAULT '',
    plan_allowed_prompts_json TEXT NOT NULL DEFAULT '[]',
    system_prompt_override TEXT NOT NULL DEFAULT '',
    system_prompt_overridden INTEGER NOT NULL DEFAULT 0,
    permission_profile_override TEXT NOT NULL DEFAULT '',
    permission_mode_override TEXT NOT NULL DEFAULT '',
    permission_restrict_allowed_tools INTEGER NOT NULL DEFAULT 0,
    permission_allowed_tools_override_json TEXT NOT NULL DEFAULT '[]',
    permission_denied_tools_override_json TEXT NOT NULL DEFAULT '[]',
    approval_required_tools_override_json TEXT NOT NULL DEFAULT '[]',
    permission_overridden INTEGER NOT NULL DEFAULT 0,
    enabled_skills_json TEXT NOT NULL DEFAULT '[]',
    enabled_plugins_json TEXT NOT NULL DEFAULT '[]',
    skill_tools_json TEXT NOT NULL DEFAULT '{}',
    plugin_tools_json TEXT NOT NULL DEFAULT '{}',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY(tenant_id, user_id, agent_id, workspace_id)
);

CREATE INDEX IF NOT EXISTS idx_session_states_scope
ON session_states(tenant_id, user_id, agent_id, workspace_id, updated_at);

CREATE TABLE IF NOT EXISTS sandbox_leases (
    lease_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    tenant_id TEXT NOT NULL DEFAULT '',
    user_id TEXT NOT NULL DEFAULT '',
    agent_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    run_id TEXT NOT NULL DEFAULT '',
    task_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    profile_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    expires_at REAL
);

CREATE INDEX IF NOT EXISTS idx_sandbox_leases_scope
ON sandbox_leases(tenant_id, user_id, agent_id, workspace_id, created_at);

CREATE INDEX IF NOT EXISTS idx_sandbox_leases_run
ON sandbox_leases(run_id, task_id, created_at);

CREATE TABLE IF NOT EXISTS sandbox_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lease_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    run_id TEXT NOT NULL DEFAULT '',
    task_id TEXT NOT NULL DEFAULT '',
    tool_call_id TEXT NOT NULL DEFAULT '',
    tool_name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    duration_ms REAL NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY(lease_id) REFERENCES sandbox_leases(lease_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sandbox_events_lease
ON sandbox_events(lease_id, created_at);

CREATE INDEX IF NOT EXISTS idx_sandbox_events_run
ON sandbox_events(run_id, task_id, created_at);

CREATE TABLE IF NOT EXISTS sandbox_workspace_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    lease_id TEXT NOT NULL,
    run_id TEXT NOT NULL DEFAULT '',
    task_id TEXT NOT NULL DEFAULT '',
    phase TEXT NOT NULL DEFAULT '',
    file_count INTEGER NOT NULL DEFAULT 0,
    total_bytes INTEGER NOT NULL DEFAULT 0,
    manifest_json TEXT NOT NULL,
    diff_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    FOREIGN KEY(lease_id) REFERENCES sandbox_leases(lease_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sandbox_workspace_snapshots_run
ON sandbox_workspace_snapshots(run_id, task_id, created_at);

CREATE TABLE IF NOT EXISTS artifact_records (
    artifact_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT '',
    user_id TEXT NOT NULL DEFAULT '',
    agent_id TEXT NOT NULL DEFAULT '',
    workspace_id TEXT NOT NULL DEFAULT '',
    run_id TEXT NOT NULL DEFAULT '',
    task_id TEXT NOT NULL DEFAULT '',
    tool_call_id TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT 'file',
    role TEXT NOT NULL DEFAULT 'tool_artifact',
    storage_backend TEXT NOT NULL DEFAULT 'local',
    uri TEXT NOT NULL DEFAULT '',
    workspace_path TEXT NOT NULL DEFAULT '',
    mime_type TEXT NOT NULL DEFAULT '',
    size_bytes INTEGER NOT NULL DEFAULT 0,
    sha256 TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL
);

CREATE INDEX IF NOT EXISTS idx_artifact_records_run
ON artifact_records(run_id, task_id, created_at);

CREATE INDEX IF NOT EXISTS idx_artifact_records_scope
ON artifact_records(tenant_id, user_id, agent_id, workspace_id, created_at);

CREATE TABLE IF NOT EXISTS credential_refs (
    credential_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL DEFAULT '',
    agent_id TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL,
    name TEXT NOT NULL,
    secret_ref TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_credential_refs_scope
ON credential_refs(tenant_id, user_id, agent_id, provider, name);
"""
