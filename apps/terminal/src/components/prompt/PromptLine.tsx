import React from 'react'
import {Box, Text, useStdout} from 'ink'
import {charAt, charLength, displayWidth, sliceChars} from '../../ui/textBuffer.js'
import {colors, glyphs} from '../../ui/theme.js'
import {cursorPositionFor, fallbackTextColumns, useAnchoredCursor, usePromptInputAnchor} from './promptCursor.js'

export function PromptLine({
  disabled,
  value,
  cursor,
  before,
  current,
  after,
  placeholder,
  argumentHint
}: {
  disabled?: boolean
  value: string
  cursor?: number
  before: string
  current: string
  after: string
  placeholder: string
  argumentHint?: string
}) {
  const {stdout} = useStdout()
  const terminalColumns = typeof stdout.columns === 'number' ? stdout.columns : 80
  const promptPrefix = `${glyphs.prompt} `
  const inputAnchor = usePromptInputAnchor()
  const textColumns = inputAnchor.columns ?? fallbackTextColumns(terminalColumns, displayWidth(promptPrefix))
  const cursorOffset = Math.max(0, Math.min(cursor ?? charLength(before), charLength(value)))
  const cursorPosition = cursorPositionFor(value, cursorOffset, textColumns)
  const active = Boolean(!disabled)
  useAnchoredCursor({active, anchorRef: inputAnchor.nodeRef, line: cursorPosition.line, column: cursorPosition.column})
  const renderedBefore = cursor === undefined ? before : sliceChars(value, 0, cursorOffset)
  const renderedCurrent = cursor === undefined ? current : charAt(value, cursorOffset) ?? ' '
  const renderedAfter = cursor === undefined ? after : sliceChars(value, cursorOffset + (charAt(value, cursorOffset) ? 1 : 0))

  return (
    <Box
      borderStyle="bold"
      borderColor={disabled ? colors.dim : colors.accent}
      borderDimColor={disabled}
      paddingX={1}
      flexShrink={0}
      width="100%"
      aria-role="textbox"
      aria-state={{disabled: Boolean(disabled)}}
    >
      <Text color={disabled ? colors.dim : colors.cyan} dimColor={disabled} bold>{promptPrefix}</Text>
      <Box ref={inputAnchor.ref} flexGrow={1} flexShrink={1} flexWrap="wrap">
        {value ? (
          <Text wrap="wrap">
            {renderedBefore}
            {renderedCurrent}
            {renderedAfter}
          </Text>
        ) : (
          <Text wrap="wrap">
            <Text> </Text>
            <Text dimColor>{placeholder}</Text>
          </Text>
        )}
        {argumentHint ? <Text dimColor> {argumentHint}</Text> : null}
      </Box>
    </Box>
  )
}
