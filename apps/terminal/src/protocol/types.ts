export type RuntimeInfo = {
  protocol: string
  model: string
  model_profile?: string
  endpoint?: string
}

export type WorkspaceInfo = {
  path: string
  display: string
  tenant_id?: string
  user_id?: string
  agent_id?: string
  workspace_id?: string
}

export type RuntimeEvent = {
  type: string
  name?: string
  payload?: Record<string, unknown>
}

export type ApprovalDecision = 'allow_once' | 'allow_for_run' | 'deny'

export type PendingApproval = {
  runId: string
  approvalId: string
  toolName: string
  args: Record<string, unknown>
  risk?: string
  reason?: string
}

export type ModelProfile = {
  name: string
  protocol: string
  model: string
  endpoint?: string
  configured?: boolean
  active?: boolean
}

export type CommandDefinition = {
  name: string
  description?: string
  action?: string
  aliases?: string[]
  argumentHint?: string
  availability?: 'idle' | 'always'
  source?: string
  category?: string
}

export type ToolDefinition = string | [string, string]

export type SessionRecord = {
  id: string
  short_id: string
  updated: string
  model: string
  messages: string
  workspace: string
}

export type BridgeEvent =
  | {
      type: 'ready'
      session_id?: string
      runtime: RuntimeInfo
      workspace: WorkspaceInfo
      profile: string
      permission: string
      sandbox: string
      tools: string[]
      commands: Array<CommandDefinition | string>
      model_profiles?: ModelProfile[]
    }
  | { type: 'turn_started'; run_id: string }
  | { type: 'runtime_event'; event: RuntimeEvent }
  | { type: 'turn_finished'; status: string; run_id?: string }
  | { type: 'model_profiles'; profiles: ModelProfile[] }
  | { type: 'model_switched'; profile: string; runtime: RuntimeInfo }
  | { type: 'runtime'; runtime: RuntimeInfo }
  | { type: 'commands'; commands: Array<CommandDefinition | string> }
  | { type: 'status'; status: Record<string, string> }
  | { type: 'doctor'; doctor: Record<string, string> }
  | { type: 'context'; context: Record<string, string> }
  | { type: 'context_messages'; messages: Array<[string, string]> }
  | { type: 'trace'; trace: Array<[string, string]> }
  | { type: 'prompt'; prompt: Array<[string, string]> }
  | { type: 'skills'; skills: Array<[string, string]> }
  | { type: 'mcp'; mcp: Array<[string, string]> }
  | { type: 'memory'; memory: Array<[string, string]> }
  | { type: 'diff'; diff: Array<[string, string]> }
  | { type: 'sessions'; sessions: SessionRecord[] }
  | { type: 'session'; session: Array<[string, string]> }
  | { type: 'agents'; agents: Array<[string, string]> }
  | { type: 'tasks'; tasks: Array<[string, string]> }
  | { type: 'schedules'; schedules: Array<[string, string]> }
  | { type: 'hooks'; hooks: Array<[string, string]> }
  | { type: 'todo'; todo: Array<[string, string]> }
  | { type: 'plan'; plan: Array<[string, string]> }
  | { type: 'workflows'; workflows: Array<[string, string]> }
  | { type: 'task_queue'; queue: Array<[string, string]> }
  | { type: 'capabilities'; capabilities: Array<[string, string]> }
  | { type: 'plugins'; plugins: Array<[string, string]> }
  | { type: 'session_resumed'; session_id: string; messages: Array<{ role: string; content: string }> }
  | { type: 'workspace'; workspace: WorkspaceInfo }
  | { type: 'tools'; tools: ToolDefinition[] }
  | { type: 'permissions'; permissions: Array<[string, string]> }
  | { type: 'notice'; message: string }
  | { type: 'error'; message: string }
  | { type: 'exit' }

export type BridgeCommand =
  | { type: 'user_message'; text: string; run_id?: string }
  | { type: 'approval'; run_id: string; approvals: Record<string, boolean>; approval_scopes: Record<string, ApprovalDecision> }
  | { type: 'slash'; text: string }
  | { type: 'cancel'; run_id?: string }
  | { type: 'exit' }
