import type {CommandDefinition} from '../protocol/terminalHostProtocol.js'

export type CommandDef = {
  kind?: 'command' | 'file' | 'model'
  name: string
  description: string
  aliases?: string[]
  argumentHint?: string
  local?: boolean
  availability?: 'idle' | 'always'
  insertText?: string
  active?: boolean
  source?: string
  category?: string
}

export const LOCAL_COMMANDS: CommandDef[] = [
  {name: '/help', description: 'show commands', local: true, availability: 'always'},
  {name: '/fold', description: 'collapse long blocks', local: true, availability: 'always'},
  {name: '/unfold', description: 'expand long blocks', local: true, availability: 'always'},
  {name: '/queue', description: 'show queued messages', local: true, availability: 'always'},
  {name: '/cancel', description: 'interrupt active run or clear queue', local: true, availability: 'always'},
  {name: '/exit', description: 'leave the chat', aliases: ['/quit'], local: true, availability: 'always'}
]

export const FALLBACK_REMOTE_COMMANDS: CommandDef[] = [
  {name: '/help', description: 'show commands', availability: 'always'},
  {name: '/commands', description: 'show or manage workspace commands', aliases: ['/cmds'], argumentHint: '[read|render|save|delete]', availability: 'idle'},
  {name: '/model', description: 'list or switch configured model profiles', argumentHint: '<profile>', availability: 'idle'},
  {name: '/status', description: 'session state'},
  {name: '/doctor', description: 'local readiness check'},
  {name: '/tools', description: 'enabled tools'},
  {name: '/permissions', description: 'show permission sources, rules, or switch permission mode', aliases: ['/permission', '/perms'], argumentHint: '[sources|audit|guarded|auto|ask|deny|allow <tool>|deny <tool>|ask <tool>|remove <tool>]'},
  {name: '/diff', description: 'show git workspace changes'},
  {name: '/workspace', description: 'workspace scope'},
  {name: '/context', description: 'show or edit context window messages', argumentHint: '[messages|drop]'},
  {name: '/trace', description: 'context assembly trace'},
  {name: '/prompt', description: 'show, override, render, or reuse prompt templates', argumentHint: '[show|set|save|render|use]'},
  {name: '/compact', description: 'summarize older conversation messages', availability: 'idle'},
  {name: '/sessions', description: 'show or delete saved terminal sessions', argumentHint: '[delete]', availability: 'idle'},
  {name: '/session', description: 'current terminal session details', availability: 'idle'},
  {name: '/summary', description: 'summarize recent session messages', argumentHint: '[max_messages]', availability: 'idle'},
  {name: '/resume', description: 'resume a saved terminal session', argumentHint: '<session>', availability: 'idle'},
  {name: '/export', description: 'export current session to JSON or Markdown', argumentHint: '[json|markdown] [path]', availability: 'idle'},
  {name: '/fork', description: 'fork current session into a new saved session', argumentHint: '[message_count]', availability: 'idle'},
  {name: '/rewind', description: 'remove recent messages from current session', argumentHint: '[count]', availability: 'idle'},
  {name: '/agents', description: 'list, save, or switch agent profiles', argumentHint: '[save|use]', availability: 'idle'},
  {name: '/tasks', description: 'list, create, run, start, queue, or cancel tasks for this agent', argumentHint: '[create|run|start|enqueue|queue|drain|cancel]', availability: 'idle'},
  {name: '/schedules', description: 'list, create, run, or delete scheduled tasks', aliases: ['/schedule'], argumentHint: '[create|run|delete]', availability: 'idle'},
  {name: '/hooks', description: 'list, add, or delete session hooks', argumentHint: '[add|delete]', availability: 'idle'},
  {name: '/todo', description: 'show or clear the session todo checklist', aliases: ['/todos'], argumentHint: '[clear]', availability: 'idle'},
  {name: '/plan', description: 'show or control session plan mode', argumentHint: '[status|enter|exit|clear]', availability: 'idle'},
  {name: '/workflows', description: 'list, save, validate, run, or delete workspace workflows', aliases: ['/workflow'], argumentHint: '[read|save|validate|run|delete]', availability: 'idle'},
  {name: '/capabilities', description: 'terminal capability surface overview', aliases: ['/caps'], availability: 'idle'},
  {name: '/plugins', description: 'install, list, enable, or disable local plugins', argumentHint: '[install|enable|disable]', availability: 'idle'},
  {name: '/skills', description: 'install, list, enable, or disable skills', argumentHint: '[install|use|disable]', availability: 'idle'},
  {name: '/mcp', description: 'show, configure, enable, disable, or reload MCP tools', argumentHint: '[set|enable|disable|remove|reload|clear]', availability: 'idle'},
  {name: '/memory', description: 'list, add, edit, or forget memory records', argumentHint: '[add|edit|forget]', availability: 'idle'},
  {name: '/clear', description: 'clear conversation', availability: 'idle'},
  {name: '/exit', description: 'leave the chat', aliases: ['/quit'], availability: 'always'}
]

export const COMMANDS = terminalCommands()

export function terminalCommands(remoteCommands?: Array<CommandDefinition | CommandDef | string>): CommandDef[] {
  const remote = remoteCommands?.length ? remoteCommands.map(normalizeCommand).filter(Boolean) as CommandDef[] : FALLBACK_REMOTE_COMMANDS
  return dedupeCommands([...LOCAL_COMMANDS, ...remote])
}

function normalizeCommand(command: CommandDefinition | CommandDef | string): CommandDef | undefined {
  if (typeof command === 'string') return {name: command, description: 'available command'}
  if (!command.name) return undefined
  const action = 'action' in command ? command.action : undefined
  return {
    name: command.name,
    description: command.description || action || 'available command',
    aliases: command.aliases,
    argumentHint: command.argumentHint,
    availability: command.availability ?? 'idle',
    source: command.source,
    category: command.category
  }
}

function dedupeCommands(commands: CommandDef[]): CommandDef[] {
  const seen = new Map<string, CommandDef>()
  for (const command of commands) {
    const existing = seen.get(command.name)
    if (!existing) {
      seen.set(command.name, command)
      continue
    }
    seen.set(command.name, {
      ...command,
      ...existing,
      aliases: Array.from(new Set([...(existing.aliases ?? []), ...(command.aliases ?? [])])),
      argumentHint: existing.argumentHint ?? command.argumentHint,
      source: existing.source ?? command.source,
      category: existing.category ?? command.category
    })
  }
  return [...seen.values()]
}
