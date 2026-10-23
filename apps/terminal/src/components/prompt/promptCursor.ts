import {useCallback, useContext, useLayoutEffect, useRef, useState} from 'react'
import type React from 'react'
import type {DOMElement} from 'ink'
import CursorContext from '../../../node_modules/ink/build/components/CursorContext.js'
import {displayWidth, graphemes, sliceChars} from '../../ui/textBuffer.js'

const ROOT_PADDING_COLUMNS = 2
const BORDER_COLUMNS = 2
const PROMPT_PADDING_COLUMNS = 2

export function usePromptInputAnchor(): {ref: (node: DOMElement | null) => void; nodeRef: React.RefObject<DOMElement | null>; columns?: number} {
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

export function useAnchoredCursor({active, anchorRef, line, column}: {active: boolean; anchorRef: React.RefObject<DOMElement | null>; line: number; column: number}) {
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

function samePosition(left: {x: number; y: number} | undefined, right: {x: number; y: number} | undefined): boolean {
  return left?.x === right?.x && left?.y === right?.y
}
