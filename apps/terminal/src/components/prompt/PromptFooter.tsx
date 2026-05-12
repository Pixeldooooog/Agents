import React from 'react'
import {Box, Text, useStdout} from 'ink'
import type {CommandDef} from '../../ui/commands.js'
import {colors} from '../../ui/theme.js'
import {ShortcutHint} from '../design/ShortcutHint.js'
import {HistorySearchLine} from './HistorySearchLine.js'
import {PromptSuggestions} from './PromptSuggestions.js'

export function PromptFooter({
  suggestions,
  selected,
  historySearch,
  disabled,
  disabledReason,
  mode = 'auto',
  maxSuggestions,
  fullscreen = false
}: {
  suggestions: CommandDef[]
  selected: number
  historySearch?: {
    active: boolean
    query: string
    match?: string
    failed?: boolean
  }
  disabled?: boolean
  disabledReason?: string
  mode?: 'auto' | 'panel' | 'hint'
  maxSuggestions?: number
  fullscreen?: boolean
}) {
  if (mode === 'hint') return <PromptHint disabled={disabled} disabledReason={disabledReason} fullscreen={fullscreen} />
  if (historySearch?.active) {
    return <HistorySearchLine query={historySearch.query} match={historySearch.match} failed={historySearch.failed} />
  }
  if (suggestions.length) {
    return <PromptSuggestions commands={suggestions} selected={selected} maxVisible={maxSuggestions} />
  }
  if (mode === 'panel') return null
  return <PromptHint disabled={disabled} disabledReason={disabledReason} fullscreen={fullscreen} />
}

function PromptHint({disabled, disabledReason, fullscreen}: {disabled?: boolean; disabledReason?: string; fullscreen?: boolean}) {
  const {stdout} = useStdout()
  const columns = typeof stdout.columns === 'number' ? stdout.columns : 80
  const items: Array<[string, string]> = [['/', 'cmd'], ['@', 'file'], ['^c', 'cancel'], [fullscreen ? 'pgup/dn' : 'terminal', 'scroll'], ['^t', 'details']]
  if (columns >= 80) items.push(['⇧↵', 'line'], ['^l', 'clear'])
  return (
    <Box paddingLeft={2}>
      {disabled ? (
        <Text dimColor>{disabledReason || 'waiting for current turn'}</Text>
      ) : (
        <ShortcutHint items={items} />
      )}
      <Text color={colors.dim}> </Text>
    </Box>
  )
}
