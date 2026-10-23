import {COMMANDS, type CommandDef} from './commandCatalog.js'

export function commandHelpRows(commands: CommandDef[] = COMMANDS): Array<[string, string]> {
  return commands.map(command => {
    const parts = [command.description]
    if (command.argumentHint) parts.push(command.argumentHint)
    if (command.local) parts.push('local')
    if (command.source && command.source !== 'builtin') parts.push(command.source)
    if ((command.availability ?? 'idle') === 'idle') parts.push('idle')
    return [command.name, parts.join(' · ')]
  })
}
