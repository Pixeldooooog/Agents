import {useMemo} from 'react'
import type {ModelProfile} from '../protocol/terminalHostProtocol.js'
import {commandMatches, findCommand, type CommandDef} from '../ui/commands.js'
import {isModelProfileQuery, modelProfileMatches} from '../ui/modelProfiles.js'
import {useFileSuggestions} from './useFileSuggestions.js'

export function useTextBufferSuggestions({
  repoRoot,
  value,
  cursor,
  commands,
  modelProfiles,
  historySearchActive
}: {
  repoRoot: string
  value: string
  cursor: number
  commands?: CommandDef[]
  modelProfiles?: ModelProfile[]
  historySearchActive: boolean
}) {
  const fileSuggestions = useFileSuggestions({repoRoot, value, cursor})
  const modelSuggestions = useMemo(() => modelProfileMatches(value, modelProfiles ?? []), [modelProfiles, value])
  const commandSuggestions = useMemo(() => commandMatches(value, commands), [commands, value])
  const suggestions = useMemo(() => {
    if (historySearchActive) return []
    if (fileSuggestions.active) return fileSuggestions.suggestions
    if (isModelProfileQuery(value)) return modelSuggestions
    return commandSuggestions
  }, [commandSuggestions, fileSuggestions.active, fileSuggestions.suggestions, historySearchActive, modelSuggestions, value])
  const activeCommand = fileSuggestions.active ? undefined : findCommand(value, commands)

  return {fileSuggestions, suggestions, activeCommand}
}
