import React from 'react'
import {Box, Text, useStdout} from 'ink'
import {AssistantMessage} from './messages/AssistantMessage.js'
import {ModelProfilesMessage} from './messages/ModelProfilesMessage.js'
import {StatusMessage} from './messages/StatusMessage.js'
import {TableMessage} from './messages/TableMessage.js'
import {ThinkingMessage} from './messages/ThinkingMessage.js'
import {ToolMessage} from './messages/ToolMessage.js'
import {UserMessage} from './messages/UserMessage.js'
import type {TranscriptItem} from './messages/types.js'
import {colors} from '../ui/theme.js'

export type {TranscriptItem} from './messages/types.js'

export function MessageList({
  items,
  collapsed,
  selectedToolId,
  expandedToolIds,
  onToggleTool
}: {
  items: TranscriptItem[]
  collapsed: boolean
  selectedToolId?: string
  expandedToolIds?: Set<string>
  onToggleTool?: (id: string) => void
}) {
  return (
    <Box flexDirection="column">
      {items.map((item, index) => (
        <MessageItem
          key={index}
          item={item}
          collapsed={collapsed}
          selectedToolId={selectedToolId}
          expandedToolIds={expandedToolIds}
          onToggleTool={onToggleTool}
        />
      ))}
    </Box>
  )
}

function MessageItem({
  item,
  collapsed,
  selectedToolId,
  expandedToolIds,
  onToggleTool
}: {
  item: TranscriptItem
  collapsed: boolean
  selectedToolId?: string
  expandedToolIds?: Set<string>
  onToggleTool?: (id: string) => void
}) {
  if (item.kind === 'user') return <UserMessage text={item.text} />
  if (item.kind === 'assistant') {
    return (
      <Box flexDirection="column">
        <AssistantMessage text={item.text} collapsed={false} live={item.live} />
        {!item.live && !item.clipped ? <AssistantDivider /> : null}
      </Box>
    )
  }
  if (item.kind === 'thinking') return <ThinkingMessage text={item.text} collapsed={collapsed} />
  if (item.kind === 'tool') {
    const id = item.id || item.name
    return <ToolMessage item={item} collapsed={collapsed} selected={selectedToolId === id} expanded={expandedToolIds?.has(id)} canToggle={Boolean(onToggleTool)} />
  }
  if (item.kind === 'table') return <TableMessage title={item.title} rows={item.rows} />
  if (item.kind === 'models') return <ModelProfilesMessage profiles={item.profiles} />
  return <StatusMessage label={item.label} text={item.text} level={item.level} />
}

function AssistantDivider() {
  const {stdout} = useStdout()
  const columns = typeof stdout.columns === 'number' ? stdout.columns : 80
  const width = Math.max(16, Math.min(96, columns - 4))
  return (
    <Box marginTop={1}>
      <Text color={colors.dim}>{'-'.repeat(width)}</Text>
    </Box>
  )
}
