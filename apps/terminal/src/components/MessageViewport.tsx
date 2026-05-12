import React from 'react'
import {Box, Text} from 'ink'
import {MessageList, type TranscriptItem} from './MessageList.js'
import {displayWidth} from '../ui/textBuffer.js'

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

export function estimateTranscriptLines(items: TranscriptItem[], collapsed: boolean, expandedToolIds?: Set<string>, columns = 100): number {
  return items.reduce((total, item) => total + estimateItemLines(item, collapsed, expandedToolIds, columns), 0)
}

function transcriptWindow(
  items: TranscriptItem[],
  height: number,
  scrollOffset: number,
  collapsed: boolean,
  selectedToolId?: string,
  expandedToolIds?: Set<string>,
  columns = 100
): {items: TranscriptItem[]; hiddenBefore: boolean} {
  if (!items.length) return {items, hiddenBefore: false}
  const lineCounts = items.map(item => estimateItemLines(item, collapsed, expandedToolIds, columns))
  const selectedIndex = selectedToolId && expandedToolIds?.has(selectedToolId)
    ? items.findIndex(item => item.kind === 'tool' && (item.id || item.name) === selectedToolId)
    : -1
  if (selectedIndex >= 0) {
    const budget = Math.max(1, height - (selectedIndex > 0 ? 1 : 0))
    const visible: TranscriptItem[] = [items[selectedIndex]]
    let used = lineCounts[selectedIndex]
    for (let index = selectedIndex + 1; index < items.length && used < budget; index++) {
      const count = lineCounts[index]
      if (used + count > budget && visible.length) break
      visible.push(items[index])
      used += count
    }
    return clipLongTextItem(visible, height, 0, selectedIndex > 0)
  }
  const totalLines = lineCounts.reduce((total, count) => total + count, 0)
  const bottomLine = Math.max(0, totalLines - scrollOffset)
  const bottomMarkerLines = scrollOffset > 0 ? 1 : 0
  let budget = Math.max(1, height - bottomMarkerLines)
  let endIndex = items.length - 1
  let cursor = 0
  for (let index = 0; index < items.length; index++) {
    const next = cursor + lineCounts[index]
    if (next >= bottomLine) {
      endIndex = index
      break
    }
    cursor = next
  }
  if (!isSubstantiveItem(items[endIndex])) {
    const substantiveIndex = findPreviousSubstantiveIndex(items, endIndex)
    if (substantiveIndex >= 0) endIndex = substantiveIndex
  }
  const visible: TranscriptItem[] = []
  let used = 0
  let startIndex = endIndex
  for (let index = endIndex; index >= 0; index--) {
    const count = lineCounts[index]
    if (visible.length && used + count > budget) {
      startIndex = index + 1
      break
    }
    visible.unshift(items[index])
    used += count
    startIndex = index
  }
  let hiddenBefore = startIndex > 0
  if (hiddenBefore && used >= budget && visible.length > 1) {
    visible.shift()
    startIndex += 1
    used = visible.reduce((total, item) => total + estimateItemLines(item, collapsed, expandedToolIds, columns), 0)
  }
  hiddenBefore = startIndex > 0
  if (hiddenBefore) {
    budget = Math.max(1, height - bottomMarkerLines - 1)
    while (visible.length > 1 && used > budget) {
      const removed = visible.shift()
      if (!removed) break
      startIndex += 1
      used -= estimateItemLines(removed, collapsed, expandedToolIds, columns)
    }
  }
  return clipLongTextItem(visible.length ? visible : items.slice(-1), height, scrollOffset, hiddenBefore)
}

function clipLongTextItem(items: TranscriptItem[], height: number, scrollOffset: number, hiddenBefore: boolean): {items: TranscriptItem[]; hiddenBefore: boolean} {
  if (items.length !== 1) return {items, hiddenBefore}
  const item = items[0]
  if (item.kind !== 'assistant' && item.kind !== 'user') return {items, hiddenBefore}
  const lines = splitLines(item.text)
  const bottomMarkerRows = scrollOffset > 0 ? 1 : 0
  let textBudget = Math.max(1, height - (hiddenBefore ? 1 : 0) - bottomMarkerRows - textHeaderLines(item))
  if (lines.length <= textBudget) return {items, hiddenBefore}
  let range = visibleTextRange(lines.length, textBudget, scrollOffset)
  if (!hiddenBefore && range.start > 0) {
    textBudget = Math.max(1, height - 1 - bottomMarkerRows - textHeaderLines(item))
    range = visibleTextRange(lines.length, textBudget, scrollOffset)
  }
  const text = lines.slice(range.start, range.end).join('\n')
  return {
    items: [item.kind === 'assistant' ? {...item, text, clipped: range.end < lines.length} : {...item, text}],
    hiddenBefore: hiddenBefore || range.start > 0
  }
}

function estimateItemLines(item: TranscriptItem, collapsed: boolean, expandedToolIds?: Set<string>, columns = 100): number {
  if (item.kind === 'user') return 3 + visualLineCount(item.text, columns - 4)
  if (item.kind === 'assistant') return 3 + visualLineCount(item.text, columns - 8) + (item.live ? 0 : 1)
  if (item.kind === 'thinking') return collapsed ? 1 : 2 + Math.min(5, visualLineCount(item.text, columns - 8))
  if (item.kind === 'status') return 2
  if (item.kind === 'table') return 2 + item.rows.length
  if (item.kind === 'models') return 2 + item.profiles.length
  if (item.kind === 'tool') {
    const id = item.id || item.name
    const expanded = id ? expandedToolIds?.has(id) : false
    return 2 + (item.result ? 2 : 0) + (expanded ? 12 : 0)
  }
  return 1
}

function findPreviousSubstantiveIndex(items: TranscriptItem[], beforeOrAt: number): number {
  for (let index = beforeOrAt; index >= 0; index--) {
    if (isSubstantiveItem(items[index])) return index
  }
  return -1
}

function isSubstantiveItem(item: TranscriptItem | undefined): boolean {
  if (!item) return false
  return item.kind !== 'status' || item.level === 'error' || item.level === 'warning'
}

function visualLineCount(text: string, columns: number): number {
  const width = Math.max(1, columns)
  return splitLines(text).reduce((total, line) => total + Math.max(1, Math.ceil(displayWidth(line) / width)), 0)
}

function splitLines(text: string): string[] {
  return text.split(/\r?\n/)
}

function textHeaderLines(item: Extract<TranscriptItem, {kind: 'assistant' | 'user'}>): number {
  return item.kind === 'assistant' ? 2 : 1
}

function visibleTextRange(lineCount: number, budget: number, scrollOffset: number): {start: number; end: number} {
  const maxOffset = Math.max(0, lineCount - budget)
  const offset = Math.min(maxOffset, Math.max(0, scrollOffset))
  const end = Math.max(budget, lineCount - offset)
  return {start: Math.max(0, end - budget), end}
}
