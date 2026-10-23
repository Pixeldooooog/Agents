import {COMMANDS, type CommandDef} from './commandCatalog.js'

export function commandMatches(value: string, commands: CommandDef[] = COMMANDS): CommandDef[] {
  if (!value.startsWith('/')) return []
  if (/^\/\S+\s/.test(value)) return []
  const [command] = value.split(/\s+/, 1)
  return commands
    .filter(item => item.name.startsWith(command || '/') || item.aliases?.some(alias => alias.startsWith(command || '/')))
    .slice(0, 9)
    .map(item => ({...item, kind: 'command'}))
}

export function findCommand(value: string, commands: CommandDef[] = COMMANDS): CommandDef | undefined {
  const [command] = value.trim().split(/\s+/, 1)
  return commands.find(item => item.name === command || item.aliases?.includes(command))
}

export function isCommandAvailableWhileBusy(value: string, commands: CommandDef[] = COMMANDS): boolean {
  const command = findCommand(value, commands)
  const text = value.trim()
  return command?.availability === 'always' && (text === command.name || Boolean(command.aliases?.includes(text)))
}
