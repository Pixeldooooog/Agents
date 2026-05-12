import React, {useEffect, useMemo, useRef} from 'react'
import {Box, useStdout} from 'ink'
import {useTextBuffer} from '../hooks/useTextBuffer.js'
import type {ModelProfile} from '../protocol/types.js'
import type {CommandDef} from '../ui/commands.js'
import {charLength, displayWidth} from '../ui/textBuffer.js'
import {Divider} from './design/Divider.js'
import {PromptFooter} from './prompt/PromptFooter.js'
import {PromptLine, cursorPositionFor, fallbackTextColumns} from './prompt/PromptLine.js'

export type PromptOverlayState = {
  suggestions: CommandDef[]
  selected: number
  historySearch?: {
    active: boolean
    query: string
    match?: string
    failed?: boolean
  }
}

export function PromptInput({
  disabled,
  disabledReason,
  repoRoot,
  commands,
  modelProfiles,
  history,
  onSubmit,
  onExit,
  onCancel,
  onClearScreen,
  onModelPicker,
  overlayMode = false,
  onOverlayChange,
  onRowsChange
}: {
  disabled?: boolean
  disabledReason?: string
  repoRoot: string
  commands?: CommandDef[]
  modelProfiles?: ModelProfile[]
  history?: string[]
  onSubmit: (value: string, displayValue?: string) => void
  onExit: () => void | boolean
  onCancel?: () => void | boolean
  onClearScreen?: () => void
  onModelPicker?: () => void
  overlayMode?: boolean
  onOverlayChange?: (overlay: PromptOverlayState | null) => void
  onRowsChange?: (rows: number) => void
}) {
  const buffer = useTextBuffer({disabled, repoRoot, commands, modelProfiles, history, onSubmit, onExit, onCancel, onClearScreen, onModelPicker})
  const {stdout} = useStdout()
  const columns = typeof stdout.columns === 'number' ? stdout.columns : 80
  const placeholder = disabled ? disabledReason || 'waiting…' : 'ask or type / for commands'
  const panel = <PromptFooter mode="panel" suggestions={buffer.suggestions} selected={buffer.selected} historySearch={buffer.historySearch} disabled={disabled} disabledReason={disabledReason} />
  const canRenderPanel = columns >= 40
  const hasPanel = !disabled && canRenderPanel && (buffer.historySearch?.active || buffer.suggestions.length > 0)
  const argumentHint = buffer.activeCommand?.argumentHint && buffer.value === buffer.activeCommand.name ? buffer.activeCommand.argumentHint : undefined
  const overlay = useMemo<PromptOverlayState | null>(() => {
    if (!overlayMode || !hasPanel) return null
    return {
      suggestions: buffer.suggestions,
      selected: buffer.selected,
      historySearch: buffer.historySearch
    }
  }, [buffer.historySearch, buffer.selected, buffer.suggestions, hasPanel, overlayMode])
  const overlayRef = useRef<PromptOverlayState | null>(null)
  overlayRef.current = overlay
  const overlayKey = promptOverlayKey(overlay)
  const promptRows = estimatePromptRows(buffer.value, columns, placeholder, argumentHint)

  useEffect(() => {
    onOverlayChange?.(overlayRef.current)
  }, [onOverlayChange, overlayKey])

  useEffect(() => {
    onRowsChange?.(promptRows)
  }, [onRowsChange, promptRows])

  useEffect(() => {
    return () => {
      onOverlayChange?.(null)
      onRowsChange?.(estimatePromptRows('', columns, placeholder))
    }
  }, [columns, onOverlayChange, onRowsChange, placeholder])

  return (
    <Box flexDirection="column" flexShrink={0} width="100%">
      <Box marginBottom={0}>
        <Divider width={Math.max(1, columns - 2)} />
      </Box>
      {!overlayMode && hasPanel ? panel : null}
      <PromptLine
        disabled={disabled}
        value={buffer.value}
        cursor={buffer.cursor}
        before={buffer.before}
        current={buffer.current}
        after={buffer.after}
        placeholder={placeholder}
        argumentHint={argumentHint}
      />
      <PromptFooter mode="hint" suggestions={buffer.suggestions} selected={buffer.selected} historySearch={buffer.historySearch} disabled={disabled} disabledReason={disabledReason} fullscreen={overlayMode} />
    </Box>
  )
}

function promptOverlayKey(overlay: PromptOverlayState | null): string {
  if (!overlay) return ''
  if (overlay.historySearch?.active) {
    return `history:${overlay.historySearch.query}:${overlay.historySearch.match ?? ''}:${overlay.historySearch.failed ? '1' : '0'}`
  }
  return `suggestions:${overlay.selected}:${overlay.suggestions.map(item => `${item.kind ?? ''}:${item.name}:${item.description}:${item.insertText ?? ''}`).join('|')}`
}

export function PromptInputOverlay({overlay, rows}: {overlay: PromptOverlayState | null; rows: number}) {
  if (!overlay || rows <= 0) return null
  return (
    <Box height={rows} flexShrink={0} flexDirection="column" overflowY="hidden">
      <PromptFooter
        mode="panel"
        suggestions={overlay.suggestions}
        selected={overlay.selected}
        historySearch={overlay.historySearch}
        maxSuggestions={Math.max(1, rows - 4)}
      />
    </Box>
  )
}

export function estimatePromptRows(value: string, terminalColumns: number, placeholder = '', argumentHint?: string): number {
  const promptPrefixColumns = displayWidth('❯ ')
  const textColumns = fallbackTextColumns(terminalColumns, promptPrefixColumns)
  const measured = value ? `${value}${argumentHint ? ` ${argumentHint}` : ''}` : placeholder
  const contentRows = cursorPositionFor(measured, charLength(measured), textColumns).line + 1
  return 4 + Math.max(1, contentRows)
}
