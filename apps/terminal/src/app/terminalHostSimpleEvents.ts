import type {TerminalHostEvent, ToolDefinition} from '../protocol/terminalHostProtocol.js'
import {terminalCommands} from '../ui/commands.js'
import {transcriptFromSession} from '../ui/sessionTranscript.js'
import type {TerminalHostEventContext} from './terminalHostEventHandlers.js'

export function handleSimpleTerminalHostEvent(event: TerminalHostEvent, context: TerminalHostEventContext): void {
  if (event.type === 'status') appendTable(context, 'Status', event.status)
  else if (event.type === 'doctor') appendTable(context, 'Doctor', event.doctor)
  else if (event.type === 'context') appendTable(context, 'Context', event.context)
  else if (event.type === 'context_messages') context.append({kind: 'table', title: 'Context Messages', rows: event.messages})
  else if (event.type === 'trace') context.append({kind: 'table', title: 'Context Trace', rows: event.trace})
  else if (event.type === 'prompt') context.append({kind: 'table', title: 'Prompt', rows: event.prompt})
  else if (event.type === 'skills') context.append({kind: 'table', title: 'Skills', rows: event.skills})
  else if (event.type === 'mcp') context.append({kind: 'table', title: 'MCP', rows: event.mcp})
  else if (event.type === 'memory') context.append({kind: 'table', title: 'Memory', rows: event.memory})
  else if (event.type === 'diff') context.append({kind: 'table', title: 'Diff', rows: event.diff})
  else if (event.type === 'session') context.append({kind: 'table', title: 'Session', rows: event.session})
  else if (event.type === 'agents') context.append({kind: 'table', title: 'Agents', rows: event.agents})
  else if (event.type === 'tasks') context.append({kind: 'table', title: 'Tasks', rows: event.tasks})
  else if (event.type === 'schedules') context.append({kind: 'table', title: 'Schedules', rows: event.schedules})
  else if (event.type === 'hooks') context.append({kind: 'table', title: 'Hooks', rows: event.hooks})
  else if (event.type === 'todo') context.append({kind: 'table', title: 'Todo', rows: event.todo})
  else if (event.type === 'plan') context.append({kind: 'table', title: 'Plan', rows: event.plan})
  else if (event.type === 'workflows') context.append({kind: 'table', title: 'Workflows', rows: event.workflows})
  else if (event.type === 'task_queue') context.append({kind: 'table', title: 'Task Queue', rows: event.queue})
  else if (event.type === 'capabilities') context.append({kind: 'table', title: 'Capabilities', rows: event.capabilities})
  else if (event.type === 'plugins') context.append({kind: 'table', title: 'Plugins', rows: event.plugins})
  else if (event.type === 'session_resumed') handleSessionResumed(event, context)
  else if (event.type === 'workspace') appendTable(context, 'Workspace', event.workspace)
  else if (event.type === 'tools') context.append({kind: 'table', title: 'Tools', rows: toolRows(event.tools)})
  else if (event.type === 'permissions') context.append({kind: 'table', title: 'Permissions', rows: event.permissions})
  else if (event.type === 'commands') handleCommands(event, context)
  else if (event.type === 'notice') context.append({kind: 'status', label: 'notice', text: event.message})
  else if (event.type === 'error') context.append({kind: 'status', label: 'error', text: event.message, level: 'error'})
  else if (event.type === 'exit') context.exit()
}

function handleSessionResumed(event: Extract<TerminalHostEvent, {type: 'session_resumed'}>, context: TerminalHostEventContext): void {
  context.setItems(transcriptFromSession(event.messages))
  context.runtimeEvents.resetLiveState()
  context.setPendingApproval(null)
  context.setSessionPicker(null)
}

function handleCommands(event: Extract<TerminalHostEvent, {type: 'commands'}>, context: TerminalHostEventContext): void {
  const nextCommands = terminalCommands(event.commands)
  context.setCommands(nextCommands)
  context.append({kind: 'table', title: 'Commands', rows: nextCommands.map(command => [command.name, command.description])})
}

function appendTable(context: TerminalHostEventContext, title: string, rows: Record<string, unknown>): void {
  context.append({kind: 'table', title, rows: Object.entries(rows).map(([key, value]) => [key, String(value)])})
}

function toolRows(tools: ToolDefinition[]): Array<[string, string]> {
  return tools.map(tool => Array.isArray(tool) ? [String(tool[0]), String(tool[1])] : [tool, 'enabled'])
}
