import React from 'react'
import {MessageList, type TranscriptItem} from '../components/MessageList.js'
import {MessageViewport} from '../components/MessageViewport.js'

export function TerminalTranscript({
  scrollableLayout,
  items,
  collapsed,
  selectedToolId,
  expandedToolIds,
  onToggleTool,
  messageRows,
  scrollOffset,
  terminalColumns
}: {
  scrollableLayout: boolean
  items: TranscriptItem[]
  collapsed: boolean
  selectedToolId?: string
  expandedToolIds: Set<string>
  onToggleTool: (id: string) => void
  messageRows: number
  scrollOffset: number
  terminalColumns: number
}) {
  if (scrollableLayout) {
    return (
      <MessageViewport
        items={items}
        collapsed={collapsed}
        selectedToolId={selectedToolId}
        expandedToolIds={expandedToolIds}
        onToggleTool={onToggleTool}
        height={messageRows}
        scrollOffset={scrollOffset}
        columns={terminalColumns}
      />
    )
  }

  return (
    <MessageList
      items={items}
      collapsed={collapsed}
      selectedToolId={selectedToolId}
      expandedToolIds={expandedToolIds}
      onToggleTool={onToggleTool}
    />
  )
}
