import React from 'react'
import {Box, Text} from 'ink'
import figures from 'figures'
import type {CommandDef} from '../../ui/commands.js'
import {colors} from '../../ui/theme.js'

export function PromptSuggestions({
  commands,
  selected,
  maxVisible = 6
}: {
  commands: CommandDef[]
  selected: number
  maxVisible?: number
}) {
  if (!commands.length) return null
  const start = Math.max(0, Math.min(selected - Math.floor(maxVisible / 2), commands.length - maxVisible))
  const visible = commands.slice(start, start + maxVisible)
  const title = suggestionTitle(commands)

  return (
    <Box flexDirection="column" marginTop={1} marginLeft={1} borderStyle="round" borderColor={colors.dim} paddingX={1} width={86}>
      <Box>
        <Text color={colors.accent} bold>{title}</Text>
        <Text dimColor>  tab to accept · ↑/↓ to move</Text>
      </Box>
      {visible.map(command => {
        const index = commands.indexOf(command)
        const active = index === selected
        if (command.kind === 'file') {
          return (
            <Box key={command.name}>
              <Text color={active ? colors.accent : colors.dim}>{active ? figures.pointer : ' '} @ </Text>
              <Text color={active ? colors.cyan : undefined}>{command.name}</Text>
              <Text dimColor>  {command.description}</Text>
            </Box>
          )
        }
        if (command.kind === 'model') {
          return (
            <Box key={command.name}>
              <Text color={active ? colors.accent : colors.dim}>{active ? figures.pointer : ' '} {command.active ? '●' : ' '} </Text>
              <Text color={active ? colors.cyan : undefined}>{command.name.padEnd(18)}</Text>
              <Text dimColor>{command.description}</Text>
              {command.argumentHint ? <Text dimColor>  {command.argumentHint}</Text> : null}
            </Box>
          )
        }
        return (
          <Box key={command.name}>
            <Text color={active ? colors.accent : colors.dim}>{active ? figures.pointer : ' '} {command.name.padEnd(13)}</Text>
            {command.local ? <Text dimColor>[local] </Text> : null}
            {command.availability === 'idle' ? <Text dimColor>[idle] </Text> : null}
            <Text color={active ? colors.cyan : colors.dim}>{command.description}</Text>
            {command.argumentHint ? <Text color={colors.dim}>  {command.argumentHint}</Text> : null}
          </Box>
        )
      })}
    </Box>
  )
}

function suggestionTitle(commands: CommandDef[]): string {
  if (commands.some(command => command.kind === 'file')) return 'Files'
  if (commands.some(command => command.kind === 'model')) return 'Model profiles'
  return 'Commands'
}
