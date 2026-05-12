import React, {useCallback, useContext, useLayoutEffect, useRef, useState} from 'react'
import {Box, Text, useStdout, type DOMElement} from 'ink'
import CursorContext from '../../../node_modules/ink/build/components/CursorContext.js'
import {charAt, charLength, displayWidth, graphemes, sliceChars} from '../../ui/textBuffer.js'
import {colors, glyphs} from '../../ui/theme.js'

const ROOT_PADDING_COLUMNS = 2
const BORDER_COLUMNS = 2
const PROMPT_PADDING_COLUMNS = 2

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

function usePromptInputAnchor(): {ref: (node: DOMElement | null) => void; nodeRef: React.RefObject<DOMElement | null>; columns?: number} {
  const nodeRef = useRef<DOMElement | null>(null)
  const columnsRef = useRef<number | undefined>(undefined)
  const [columns, setColumns] = useState<number>()
  const commitColumns = useCallback((next: number | undefined) => {
    if (next === undefined || next === columnsRef.current) return
    columnsRef.current = next
    setColumns(next)
  }, [])
  const setNode = useCallback((node: DOMElement | null) => {
    nodeRef.current = node
    if (node) commitColumns(measuredColumns(node))
  }, [commitColumns])
  useLayoutEffect(() => {
    commitColumns(measuredColumns(nodeRef.current))
  })
  return {
    ref: setNode,
    nodeRef,
    columns
  }
}

function useAnchoredCursor({active, anchorRef, line, column}: {active: boolean; anchorRef: React.RefObject<DOMElement | null>; line: number; column: number}) {
  const {setCursorPosition} = useContext(CursorContext)
  const declaration = useRef({active, line, column})
  const appliedPosition = useRef<{x: number; y: number} | undefined>(undefined)
  const setCursorPositionRef = useRef(setCursorPosition)
  setCursorPositionRef.current = setCursorPosition
  declaration.current = {active, line, column}

  const applyCursor = useCallback(() => {
    const origin = absolutePosition(anchorRef.current)
    const current = declaration.current
    const next = current.active && origin ? {x: origin.x + current.column, y: origin.y + current.line} : undefined
    if (samePosition(appliedPosition.current, next)) return
    appliedPosition.current = next
    setCursorPositionRef.current(next)
  }, [anchorRef])

  useLayoutEffect(() => {
    const root = rootNode(anchorRef.current)
    if (!root) {
      applyCursor()
      return
    }
    const original = root.onComputeLayout
    const wrapped = () => {
      original?.()
      applyCursor()
    }
    root.onComputeLayout = wrapped
    applyCursor()
    return () => {
      if (root.onComputeLayout === wrapped) root.onComputeLayout = original
      appliedPosition.current = undefined
      setCursorPositionRef.current(undefined)
    }
  }, [anchorRef, applyCursor])
}

function samePosition(left: {x: number; y: number} | undefined, right: {x: number; y: number} | undefined): boolean {
  return left?.x === right?.x && left?.y === right?.y
}

export function cursorPositionFor(value: string, cursor: number, columns: number): {line: number; column: number} {
  const width = Math.max(1, columns - 1)
  let line = 0
  let column = 0
  for (const char of graphemes(sliceChars(value, 0, cursor))) {
    if (char === '\n') {
      line += 1
      column = 0
      continue
    }
    const charWidth = Math.max(0, displayWidth(char))
    if (column > 0 && column + charWidth > width) {
      line += 1
      column = 0
    }
    column += charWidth
  }
  return {line, column}
}

export function fallbackTextColumns(terminalColumns: number, promptPrefixColumns: number): number {
  return Math.max(1, terminalColumns - ROOT_PADDING_COLUMNS - BORDER_COLUMNS - PROMPT_PADDING_COLUMNS - promptPrefixColumns)
}

function measuredColumns(node: DOMElement | null): number | undefined {
  const width = node?.yogaNode?.getComputedWidth()
  if (typeof width !== 'number' || !Number.isFinite(width) || width <= 0) return undefined
  return Math.max(1, Math.floor(width))
}

function absolutePosition(node: DOMElement | null): {x: number; y: number} | undefined {
  let current: DOMElement | undefined = node ?? undefined
  let x = 0
  let y = 0
  let measured = false

  while (current) {
    const yoga = current.yogaNode
    if (yoga) {
      x += yoga.getComputedLeft()
      y += yoga.getComputedTop()
      measured = true
    }
    current = current.parentNode
  }

  if (!measured) return undefined
  return {x: Math.max(0, Math.round(x)), y: Math.max(0, Math.round(y))}
}

function rootNode(node: DOMElement | null): DOMElement | undefined {
  let current: DOMElement | undefined = node ?? undefined
  let root: DOMElement | undefined

  while (current) {
    root = current
    current = current.parentNode
  }

  return root
}
