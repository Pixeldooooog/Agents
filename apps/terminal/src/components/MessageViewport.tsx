import React from 'react'
import {Box, Text} from 'ink'
import {MessageList, type TranscriptItem} from './MessageList.js'
import {transcriptWindow} from './messageViewportLayout.js'

export function MessageViewport({
  items,
  collapsed,
  selectedToolId,
  expandedToolIds,
  onToggleTool,
  height,
  scrollOffset,
  columns = 100
}: {
  items: TranscriptItem[]
  collapsed: boolean
  selectedToolId?: string
  expandedToolIds?: Set<string>
  onToggleTool?: (id: string) => void
  height: number
  scrollOffset: number
  columns?: number
}) {
  const window = transcriptWindow(items, height, scrollOffset, collapsed, selectedToolId, expandedToolIds, columns)
  const hasLiveOutputBelow = scrollOffset > 0 && items.some(item => item.kind === 'assistant' && item.live)
  return (
    <Box flexDirection="column" height={Math.max(1, height)} justifyContent="flex-end" overflowY="hidden">
      {window.hiddenBefore ? <Text dimColor>↑ earlier messages hidden · pgup/dn page · shift/alt+↑↓ line</Text> : null}
      <MessageList items={window.items} collapsed={collapsed} selectedToolId={selectedToolId} expandedToolIds={expandedToolIds} onToggleTool={onToggleTool} />
      {scrollOffset > 0 ? (
        <Text dimColor>
          ↓ {scrollOffset} lines above latest{hasLiveOutputBelow ? ' · new output below' : ''} · pgup/dn page · shift/alt+↑↓ line
        </Text>
      ) : null}
    </Box>
  )
}
