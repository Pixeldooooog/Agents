import React from 'react'
import {Box, Text} from 'ink'
import {colors} from '../../ui/theme.js'
import {formatDuration, toolSummary} from '../../ui/format.js'
import {MessageResponse} from '../MessageResponse.js'
import {ToolUseLoader} from '../ToolUseLoader.js'
import {ToolPreview} from '../tools/ToolPreview.js'
import {ToolResultPreview} from '../tools/ToolResultPreview.js'
import type {TranscriptItem} from './types.js'

export function ToolMessage({
  item,
  collapsed,
  selected,
  expanded,
  canToggle
}: {
  item: Extract<TranscriptItem, {kind: 'tool'}>
  collapsed: boolean
  selected: boolean
  expanded?: boolean
  canToggle?: boolean
}) {
  const status = item.error ? 'Tool Error' : item.result ? 'Tool Call' : 'Tool Running'
  const statusColor = item.error ? colors.error : item.result ? colors.success : colors.dim
  const summary = toolSummary(item.name, item.args)
  const hint = selected && canToggle ? (expanded ? 'ctrl+t next' : 'ctrl+t details') : undefined

  return (
    <Box flexDirection="column" marginTop={1}>
      <Box>
        <ToolUseLoader unresolved={!item.result} error={item.error} />
        {selected ? <Text color={colors.cyan}>▸ </Text> : <Text dimColor>  </Text>}
        <Text color={statusColor} bold>{status}</Text>
        <Text color={selected ? colors.text : undefined} bold>  {summary}</Text>
        <Text dimColor>  {item.name}</Text>
        {item.durationMs ? <Text dimColor>  {formatDuration(item.durationMs)}</Text> : null}
        {hint ? <Text color={selected ? colors.cyan : colors.dim}>  {hint}</Text> : null}
      </Box>
      {item.result ? (
        <MessageResponse>
          <Text color={item.error ? colors.error : colors.dim}>Result  {item.result}</Text>
        </MessageResponse>
      ) : null}
      {expanded ? (
        <MessageResponse>
          <Box flexDirection="column">
            <Text color={colors.cyan}>Details</Text>
            <Text color={colors.dim}>Input</Text>
            <ToolPreview name={item.name} args={item.args} collapsed={collapsed} showRaw />
            {item.detail ? (
              <>
                <Text color={colors.dim}>Raw Result</Text>
                <ToolResultPreview name={item.name} detail={item.detail} collapsed={collapsed} />
              </>
            ) : null}
          </Box>
        </MessageResponse>
      ) : null}
      {!expanded && selected && canToggle ? (
        <Box paddingLeft={4}>
          <Text dimColor>ctrl+t to inspect arguments and raw result</Text>
        </Box>
      ) : null}
    </Box>
  )
}
