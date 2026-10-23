import {useEffect, useRef, useState} from 'react'
import {useStdin} from 'ink'
import {charAt, sliceChars} from '../ui/textBuffer.js'
import {useHistoryNavigation} from './useHistoryNavigation.js'
import {useHistorySearch} from './useHistorySearch.js'
import {useSafeInput} from './useSafeInput.js'
import {useTextBufferEditor} from './useTextBufferEditor.js'
import {useTextBufferSuggestions} from './useTextBufferSuggestions.js'
import {normalizeInsertedText} from './textBufferInput.js'
import {createPasteBuffer} from './textBufferPaste.js'
import {handleTextBufferKeyInput} from './textBufferKeyInput.js'
import type {TextBufferOptions} from './textBufferTypes.js'

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
}: TextBufferOptions) {
  const [selected, setSelected] = useState(0)
  const rawInputRef = useRef('')
  const editSideEffectsRef = useRef(() => setSelected(0))
  const editor = useTextBufferEditor({onEdit: () => editSideEffectsRef.current()})
  const {value, cursor, valueRef, cursorRef} = editor
  const pasteBuffer = useRef(createPasteBuffer()).current
  const historyNavigation = useHistoryNavigation({history, value, setValue: editor.setCommittedValue, setCursor: editor.setCommittedCursor})
  const historySearch = useHistorySearch(history)
  const {isRawModeSupported, internal_eventEmitter} = useStdin()
  const {fileSuggestions, suggestions, activeCommand} = useTextBufferSuggestions({
    repoRoot,
    value,
    cursor,
    commands,
    modelProfiles,
    historySearchActive: historySearch.active
  })
  editSideEffectsRef.current = () => {
    historyNavigation.clear()
    setSelected(0)
  }

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
    handleTextBufferKeyInput({
      input,
      key,
      rawInput: rawInputRef.current,
      currentValue: valueRef.current,
      currentCursor: cursorRef.current,
      history,
      editor,
      pasteBuffer,
      historyNavigation,
      historySearch,
      suggestions,
      fileSuggestions,
      setSelected,
      insert,
      submitCurrentValue,
      acceptSelectedSuggestion,
      reset,
      acceptHistorySearch,
      onSubmit,
      onExit,
      onCancel,
      onClearScreen,
      onModelPicker
    })
  }, {isActive: Boolean(!disabled && isRawModeSupported)})

  function insert(text: string, rawInput = rawInputRef.current) {
    const normalizedText = normalizeInsertedText(text, rawInput)
    const displayText = pasteBuffer.displayTextForInput(normalizedText)
    editor.insert(displayText)
  }

  function submitCurrentValue() {
    const displayText = valueRef.current.trim()
    if (displayText) onSubmit(pasteBuffer.expandPasteRefs(displayText), displayText)
    reset()
  }

  function acceptSelectedSuggestion(submitCommands: boolean): 'none' | 'inserted' | 'submitted' {
    if (!suggestions.length) return 'none'
    const suggestion = suggestions[selected]
    if (!suggestion) return 'none'
    const next = suggestion.insertText ?? suggestion.name
    if (fileSuggestions.active && suggestion.kind === 'file') {
      editor.replaceRange(fileSuggestions.start, cursorRef.current, next)
      return 'inserted'
    }
    if (submitCommands && (suggestion.kind === 'command' || suggestion.kind === 'model')) {
      const text = next.trim()
      if (text) onSubmit(text)
      return 'submitted'
    }
    editor.replace(next)
    return 'inserted'
  }

  function acceptHistorySearch() {
    if (historySearch.match) editor.replace(historySearch.match)
    historySearch.close()
  }

  function reset() {
    pasteBuffer.clear()
    editor.resetValue()
    setSelected(0)
    historyNavigation.reset()
    historySearch.close()
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
