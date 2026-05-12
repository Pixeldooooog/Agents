import {useEffect, useMemo, useRef, useState, type SetStateAction} from 'react'
import {useStdin} from 'ink'
import {commandMatches, findCommand, type CommandDef} from '../ui/commands.js'
import type {ModelProfile} from '../protocol/types.js'
import {charAt, charLength, insertAt, isBackspaceInput, isDeleteInput, nextWordBoundary, previousWordBoundary, removeAt, removeBefore, sliceChars} from '../ui/textBuffer.js'
import {isModelProfileQuery, modelProfileMatches} from '../ui/modelProfiles.js'
import {useFileSuggestions} from './useFileSuggestions.js'
import {useHistoryNavigation} from './useHistoryNavigation.js'
import {useHistorySearch} from './useHistorySearch.js'
import {useSafeInput} from './useSafeInput.js'

const PASTE_TRUNCATION_THRESHOLD = 10000
const ANSI_PATTERN = /(?:\u001B\[[0-?]*[ -/]*[@-~]|\u001B\][\s\S]*?(?:\u0007|\u001B\\)|\u001B[()][A-Za-z0-9])/g

export function useTextBuffer({
  disabled,
  repoRoot,
  commands,
  modelProfiles,
  history,
  onSubmit,
  onExit,
  onCancel,
  onClearScreen,
  onModelPicker
}: {
  disabled?: boolean
  repoRoot: string
  commands?: CommandDef[]
  modelProfiles?: ModelProfile[]
  history?: string[]
  onSubmit: (value: string, displayValue?: string) => void
  onExit: () => void | boolean
  onCancel?: () => void | boolean
  onClearScreen?: () => void
  onModelPicker?: () => void
}) {
  const [value, setValue] = useState('')
  const [cursor, setCursor] = useState(0)
  const [selected, setSelected] = useState(0)
  const valueRef = useRef(value)
  const cursorRef = useRef(cursor)
  const rawInputRef = useRef('')
  const pasteRefs = useRef(new Map<string, string>())
  const bracketedPasteBuffer = useRef<string | null>(null)
  const nextPasteId = useRef(1)
  const historyNavigation = useHistoryNavigation({history, value, setValue: setCommittedValue, setCursor: setCommittedCursor})
  const historySearch = useHistorySearch(history)
  const {isRawModeSupported, internal_eventEmitter} = useStdin()
  const fileSuggestions = useFileSuggestions({repoRoot, value, cursor})
  const modelSuggestions = useMemo(() => modelProfileMatches(value, modelProfiles ?? []), [modelProfiles, value])
  const commandSuggestions = useMemo(() => commandMatches(value, commands), [commands, value])
  const suggestions = useMemo(() => {
    if (historySearch.active) return []
    if (fileSuggestions.active) return fileSuggestions.suggestions
    if (isModelProfileQuery(value)) return modelSuggestions
    return commandSuggestions
  }, [commandSuggestions, fileSuggestions.active, fileSuggestions.suggestions, historySearch.active, modelSuggestions, value])
  const activeCommand = fileSuggestions.active ? undefined : findCommand(value, commands)

  useEffect(() => {
    setSelected(current => Math.min(current, Math.max(0, suggestions.length - 1)))
  }, [suggestions.length])

  useEffect(() => {
    valueRef.current = value
  }, [value])

  useEffect(() => {
    cursorRef.current = cursor
  }, [cursor])

  useEffect(() => {
    const captureRawInput = (data: unknown) => {
      rawInputRef.current = Buffer.isBuffer(data) ? data.toString() : String(data ?? '')
    }
    internal_eventEmitter.on('input', captureRawInput)
    return () => {
      internal_eventEmitter.removeListener('input', captureRawInput)
    }
  }, [internal_eventEmitter])

  useSafeInput((input, key) => {
    if (disabled) return
    const currentValue = valueRef.current
    const currentCursor = cursorRef.current
    const rawInput = rawInputRef.current
    const returnKey = isReturnInput(input, key)
    if (key.pageUp || key.pageDown || key.mouse || key.wheelUp || key.wheelDown || ((key.meta || key.shift) && (key.upArrow || key.downArrow))) return
    if (handleBracketedPasteEvent(input, rawInput)) return
    const bufferedReturn = splitBufferedReturnInput(input, key)
    if (bufferedReturn) {
      if (bufferedReturn.text) insert(bufferedReturn.text)
      submitCurrentValue()
      return
    }
    if (historySearch.active) {
      handleHistorySearchInput(input, key)
      return
    }
    if (key.ctrl && input === 'c') {
      if (currentValue) {
        reset()
        return
      }
      if (onCancel?.()) reset()
      return
    }
    if (key.ctrl && input === 'd') {
      if (currentValue) {
        removeAfterCursor()
        return
      }
      if (onExit()) reset()
      return
    }
    if (key.ctrl && input === 'r') {
      historySearch.open()
      return
    }
    if (key.ctrl && input === 'l') {
      onClearScreen?.()
      return
    }
    if (key.meta && input === 'p') {
      onModelPicker?.()
      return
    }
    if (returnKey && key.shift) {
      insert('\n')
      return
    }
    if (returnKey) {
      const accepted = acceptSelectedSuggestion(true)
      if (accepted === 'submitted') {
        reset()
        return
      }
      if (accepted === 'inserted') return
      submitCurrentValue()
      return
    }
    if (key.escape && currentValue) {
      reset()
      return
    }
    if (key.escape) {
      if (onCancel?.()) reset()
      return
    }
    if (key.meta && isBackspaceInput(input, key, rawInput)) {
      removeWordBeforeCursor()
      return
    }
    if (isBackspaceInput(input, key, rawInput)) {
      removeBeforeCursor()
      return
    }
    if ((key.meta || key.ctrl) && isDeleteInput(input, key, rawInput)) {
      removeWordAfterCursor()
      return
    }
    if (isDeleteInput(input, key, rawInput)) {
      removeAfterCursor()
      return
    }
    if (key.leftArrow && (key.ctrl || key.meta)) {
      commitCursor(previousWordBoundary(currentValue, currentCursor))
      return
    }
    if (key.rightArrow && (key.ctrl || key.meta)) {
      commitCursor(nextWordBoundary(currentValue, currentCursor))
      return
    }
    if (key.home) {
      commitCursor(0)
      return
    }
    if (key.end) {
      commitCursor(charLength(currentValue))
      return
    }
    if (key.leftArrow) {
      commitCursor(currentCursor - 1)
      return
    }
    if (key.rightArrow) {
      commitCursor(currentCursor + 1)
      return
    }
    if (key.meta && input === 'b') {
      commitCursor(previousWordBoundary(currentValue, currentCursor))
      return
    }
    if (key.meta && input === 'f') {
      commitCursor(nextWordBoundary(currentValue, currentCursor))
      return
    }
    if (key.meta && input === 'd') {
      removeWordAfterCursor()
      return
    }
    if (key.ctrl && input === 'b') {
      commitCursor(currentCursor - 1)
      return
    }
    if (key.ctrl && input === 'f') {
      commitCursor(currentCursor + 1)
      return
    }
    if (key.ctrl && input === 'a') {
      commitCursor(0)
      return
    }
    if (key.ctrl && input === 'e') {
      commitCursor(charLength(currentValue))
      return
    }
    if (key.ctrl && input === 'w') {
      removeWordBeforeCursor()
      return
    }
    if (key.ctrl && input === 'u') {
      commit(sliceChars(currentValue, currentCursor), 0)
      historyNavigation.clear()
      setSelected(0)
      return
    }
    if (key.ctrl && input === 'k') {
      commit(sliceChars(currentValue, 0, currentCursor), currentCursor)
      historyNavigation.clear()
      setSelected(0)
      return
    }
    if (key.ctrl && input === 'p' && suggestions.length) {
      setSelected(current => (current - 1 + suggestions.length) % suggestions.length)
      return
    }
    if (key.ctrl && input === 'n' && suggestions.length) {
      setSelected(current => (current + 1) % suggestions.length)
      return
    }
    if (key.ctrl && input === 'p' && history?.length) {
      historyNavigation.show(-1)
      return
    }
    if (key.ctrl && input === 'n' && history?.length && historyNavigation.active) {
      historyNavigation.show(1)
      return
    }
    if (key.upArrow && suggestions.length) {
      setSelected(current => (current - 1 + suggestions.length) % suggestions.length)
      return
    }
    if (key.downArrow && suggestions.length) {
      setSelected(current => (current + 1) % suggestions.length)
      return
    }
    if (key.upArrow && history?.length) {
      historyNavigation.show(-1)
      return
    }
    if (key.downArrow && history?.length && historyNavigation.active) {
      historyNavigation.show(1)
      return
    }
    if (key.tab && suggestions.length) {
      acceptSelectedSuggestion(false)
      return
    }
    if (input && !key.meta && !key.ctrl) {
      insert(input)
    }
  }, {isActive: Boolean(!disabled && isRawModeSupported)})

  function insert(text: string, rawInput = rawInputRef.current) {
    const currentValue = valueRef.current
    const currentCursor = cursorRef.current
    const normalizedText = normalizeInsertedText(text, rawInput)
    const displayText = displayTextForInput(normalizedText)
    commit(insertAt(currentValue, currentCursor, displayText), currentCursor + charLength(displayText))
    historyNavigation.clear()
    setSelected(0)
  }

  function submitCurrentValue() {
    const displayText = valueRef.current.trim()
    if (displayText) onSubmit(expandPasteRefs(displayText), displayText)
    reset()
  }

  function replace(text: string) {
    commit(text, charLength(text))
    setSelected(0)
    historyNavigation.clear()
  }

  function replaceRange(start: number, end: number, text: string) {
    const currentValue = valueRef.current
    const next = `${sliceChars(currentValue, 0, start)}${text}${sliceChars(currentValue, end)}`
    commit(next, start + charLength(text))
    setSelected(0)
    historyNavigation.clear()
  }

  function acceptSelectedSuggestion(submitCommands: boolean): 'none' | 'inserted' | 'submitted' {
    if (!suggestions.length) return 'none'
    const suggestion = suggestions[selected]
    if (!suggestion) return 'none'
    const next = suggestion.insertText ?? suggestion.name
    if (fileSuggestions.active && suggestion.kind === 'file') {
      replaceRange(fileSuggestions.start, cursorRef.current, next)
      return 'inserted'
    }
    if (submitCommands && (suggestion.kind === 'command' || suggestion.kind === 'model')) {
      const text = next.trim()
      if (text) onSubmit(text)
      return 'submitted'
    }
    replace(next)
    return 'inserted'
  }

  function removeBeforeCursor() {
    const currentValue = valueRef.current
    const currentCursor = cursorRef.current
    if (currentCursor <= 0) return
    commit(removeBefore(currentValue, currentCursor), currentCursor - 1)
    historyNavigation.clear()
    setSelected(0)
  }

  function removeAfterCursor() {
    const currentValue = valueRef.current
    const currentCursor = cursorRef.current
    if (currentCursor >= charLength(currentValue)) return
    commit(removeAt(currentValue, currentCursor), currentCursor)
    historyNavigation.clear()
    setSelected(0)
  }

  function removeWordBeforeCursor() {
    const currentValue = valueRef.current
    const currentCursor = cursorRef.current
    if (currentCursor <= 0) return
    const start = previousWordBoundary(currentValue, currentCursor)
    commit(`${sliceChars(currentValue, 0, start)}${sliceChars(currentValue, currentCursor)}`, start)
    historyNavigation.clear()
    setSelected(0)
  }

  function removeWordAfterCursor() {
    const currentValue = valueRef.current
    const currentCursor = cursorRef.current
    if (currentCursor >= charLength(currentValue)) return
    const end = nextWordBoundary(currentValue, currentCursor)
    commit(`${sliceChars(currentValue, 0, currentCursor)}${sliceChars(currentValue, end)}`, currentCursor)
    historyNavigation.clear()
    setSelected(0)
  }

  function commit(nextValue: string, nextCursor: number) {
    const clampedCursor = clampCursor(nextValue, nextCursor)
    valueRef.current = nextValue
    cursorRef.current = clampedCursor
    setValue(nextValue)
    setCursor(clampedCursor)
  }

  function commitCursor(nextCursor: number) {
    const clampedCursor = clampCursor(valueRef.current, nextCursor)
    cursorRef.current = clampedCursor
    setCursor(clampedCursor)
  }

  function setCommittedValue(action: SetStateAction<string>) {
    setValue(current => {
      const next = typeof action === 'function' ? action(current) : action
      valueRef.current = next
      return next
    })
  }

  function setCommittedCursor(action: SetStateAction<number>) {
    setCursor(current => {
      const raw = typeof action === 'function' ? action(current) : action
      const next = clampCursor(valueRef.current, raw)
      cursorRef.current = next
      return next
    })
  }

  function clampCursor(text: string, point: number) {
    return Math.max(0, Math.min(charLength(text), point))
  }

  function handleHistorySearchInput(input: string, key: {
    return?: boolean
    escape?: boolean
    backspace?: boolean
    delete?: boolean
    mouse?: boolean
    wheelUp?: boolean
    wheelDown?: boolean
    upArrow?: boolean
    downArrow?: boolean
    ctrl?: boolean
    meta?: boolean
    shift?: boolean
    tab?: boolean
    pageUp?: boolean
    pageDown?: boolean
  }) {
    if ((key.ctrl && input === 'c') || (key.ctrl && input === 'g')) {
      historySearch.close()
      return
    }
    if (key.ctrl && input === 'r') {
      historySearch.next()
      return
    }
    if (isReturnInput(input, key)) {
      if (!historySearch.match) {
        historySearch.close()
        return
      }
      const text = historySearch.match.trim()
      if (text) onSubmit(text)
      reset()
      return
    }
    if (key.escape || key.tab) {
      acceptHistorySearch()
      return
    }
    if (key.upArrow) {
      historySearch.previous()
      return
    }
    if (key.downArrow) {
      historySearch.next()
      return
    }
    if (isBackspaceInput(input, key, rawInputRef.current) || isDeleteInput(input, key, rawInputRef.current)) {
      historySearch.backspace()
      return
    }
    if (input && !key.meta && !key.ctrl) {
      historySearch.append(input)
    }
  }

  function acceptHistorySearch() {
    if (historySearch.match) replace(historySearch.match)
    historySearch.close()
  }

  function reset() {
    pasteRefs.current.clear()
    commit('', 0)
    setSelected(0)
    historyNavigation.reset()
    historySearch.close()
  }

  function displayTextForInput(text: string): string {
    if (text.length <= PASTE_TRUNCATION_THRESHOLD) return text
    const id = nextPasteId.current++
    const reference = `[...Pasted text #${id} +${lineCount(text)} lines...]`
    pasteRefs.current.set(reference, text)
    return reference
  }

  function expandPasteRefs(text: string): string {
    let expanded = text
    for (const [reference, content] of pasteRefs.current) {
      expanded = expanded.split(reference).join(content)
    }
    return expanded
  }

  function handleBracketedPasteEvent(input: string, rawInput: string): boolean {
    const fullPaste = bracketedPasteText(rawInput)
    if (fullPaste !== undefined) {
      insert(fullPaste, '')
      return true
    }
    if (isBracketedPasteStart(input, rawInput)) {
      bracketedPasteBuffer.current = ''
      return true
    }
    if (bracketedPasteBuffer.current === null) return false
    if (isBracketedPasteEnd(input, rawInput)) {
      const pasted = normalizePastedText(bracketedPasteBuffer.current)
      bracketedPasteBuffer.current = null
      insert(pasted, '')
      return true
    }
    bracketedPasteBuffer.current += rawInput || input
    return true
  }

  return {
    value,
    cursor,
    selected,
    suggestions,
    activeCommand,
    historySearch: historySearch.state,
    before: sliceChars(value, 0, cursor),
    current: charAt(value, cursor) ?? ' ',
    after: sliceChars(value, cursor + 1)
  }
}

function isReturnInput(input: string, key: {return?: boolean}): boolean {
  return Boolean(key.return || input === '\r' || input === '\n')
}

function splitBufferedReturnInput(input: string, key: {return?: boolean}): {text: string} | undefined {
  if (!input || isReturnInput(input, key)) return undefined
  const newline = trailingNewline(input)
  if (!newline) return undefined
  const text = input.slice(0, -newline.length)
  if (!text || hasLineBreak(text)) return undefined
  return {text}
}

function trailingNewline(input: string): '\r\n' | '\r' | '\n' | undefined {
  if (input.endsWith('\r\n')) return '\r\n'
  if (input.endsWith('\r')) return '\r'
  if (input.endsWith('\n')) return '\n'
  return undefined
}

function hasLineBreak(input: string): boolean {
  return input.includes('\r') || input.includes('\n')
}

function lineCount(input: string): number {
  return input.split(/\r\n|\r|\n/).length
}

function bracketedPasteText(rawInput: string): string | undefined {
  const startToken = '\u001B[200~'
  const endToken = '\u001B[201~'
  const start = rawInput.indexOf(startToken)
  const end = rawInput.lastIndexOf(endToken)
  if (start < 0 || end < start) return undefined
  return normalizePastedText(rawInput.slice(start + startToken.length, end))
}

function isBracketedPasteStart(input: string, rawInput: string): boolean {
  return rawInput === '\u001B[200~' || input === '[200~'
}

function isBracketedPasteEnd(input: string, rawInput: string): boolean {
  return rawInput === '\u001B[201~' || input === '[201~'
}

function normalizeInsertedText(text: string, rawInput: string): string {
  const bracketed = bracketedPasteText(rawInput)
  if (bracketed !== undefined) return bracketed
  if (text.length <= 1 && !/[\r\n\t\u001B\u009B]/.test(text)) return text
  return normalizePastedText(text)
}

function normalizePastedText(text: string): string {
  return text
    .replace(ANSI_PATTERN, '')
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .replaceAll('\t', '    ')
}
