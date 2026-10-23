import type {Dispatch, SetStateAction} from 'react'
import {handleTextBufferHistorySearchInput} from './textBufferHistorySearchInput.js'
import {isReturnInput, splitBufferedReturnInput} from './textBufferInput.js'
import type {TextBufferKey, TextBufferOptions} from './textBufferTypes.js'
import {handleTextBufferEditingKey} from './textBufferEditingKeys.js'
import {handleTextBufferSelectionKey} from './textBufferSelectionKeys.js'
import type {createPasteBuffer} from './textBufferPaste.js'
import type {useHistoryNavigation} from './useHistoryNavigation.js'
import type {useHistorySearch} from './useHistorySearch.js'
import type {useTextBufferEditor} from './useTextBufferEditor.js'
import type {useTextBufferSuggestions} from './useTextBufferSuggestions.js'

type TextBufferEditor = ReturnType<typeof useTextBufferEditor>
type PasteBuffer = ReturnType<typeof createPasteBuffer>
type HistoryNavigationController = ReturnType<typeof useHistoryNavigation>
type HistorySearchController = ReturnType<typeof useHistorySearch>
type SuggestionState = ReturnType<typeof useTextBufferSuggestions>

type TextBufferKeyInputOptions = {
  input: string
  key: TextBufferKey
  rawInput: string
  currentValue: string
  currentCursor: number
  history?: string[]
  editor: TextBufferEditor
  pasteBuffer: PasteBuffer
  historyNavigation: HistoryNavigationController
  historySearch: HistorySearchController
  suggestions: SuggestionState['suggestions']
  fileSuggestions: SuggestionState['fileSuggestions']
  setSelected: Dispatch<SetStateAction<number>>
  insert: (text: string, rawInput?: string) => void
  submitCurrentValue: () => void
  acceptSelectedSuggestion: (submitCommands: boolean) => 'none' | 'inserted' | 'submitted'
  reset: () => void
  acceptHistorySearch: () => void
  onSubmit: TextBufferOptions['onSubmit']
  onExit: TextBufferOptions['onExit']
  onCancel: TextBufferOptions['onCancel']
  onClearScreen: TextBufferOptions['onClearScreen']
  onModelPicker: TextBufferOptions['onModelPicker']
}

export function handleTextBufferKeyInput(options: TextBufferKeyInputOptions) {
  const {input, key, rawInput, currentValue, currentCursor, suggestions} = options
  const returnKey = isReturnInput(input, key)
  if (isIgnoredNavigationInput(key)) return
  if (options.pasteBuffer.handleBracketedPasteEvent(input, rawInput, options.insert)) return
  const bufferedReturn = splitBufferedReturnInput(input, key)
  if (bufferedReturn) {
    if (bufferedReturn.text) options.insert(bufferedReturn.text)
    options.submitCurrentValue()
    return
  }
  if (options.historySearch.active) {
    handleTextBufferHistorySearchInput({
      input,
      key,
      rawInput,
      historySearch: options.historySearch,
      onSubmit: options.onSubmit,
      reset: options.reset,
      acceptHistorySearch: options.acceptHistorySearch
    })
    return
  }
  if (key.ctrl && input === 'c') {
    if (currentValue) {
      options.reset()
      return
    }
    if (options.onCancel?.()) options.reset()
    return
  }
  if (key.ctrl && input === 'd') {
    if (currentValue) {
      options.editor.removeAfterCursor()
      return
    }
    if (options.onExit()) options.reset()
    return
  }
  if (key.ctrl && input === 'r') {
    options.historySearch.open()
    return
  }
  if (key.ctrl && input === 'l') {
    options.onClearScreen?.()
    return
  }
  if (key.meta && input === 'p') {
    options.onModelPicker?.()
    return
  }
  if (returnKey && key.shift) {
    options.insert('\n')
    return
  }
  if (returnKey) {
    const accepted = options.acceptSelectedSuggestion(true)
    if (accepted === 'submitted') {
      options.reset()
      return
    }
    if (accepted === 'inserted') return
    options.submitCurrentValue()
    return
  }
  if (key.escape && currentValue) {
    options.reset()
    return
  }
  if (key.escape) {
    if (options.onCancel?.()) options.reset()
    return
  }
  if (handleTextBufferEditingKey({input, key, rawInput, currentValue, currentCursor, editor: options.editor})) return
  if (handleTextBufferSelectionKey({
    input,
    key,
    history: options.history,
    historyNavigation: options.historyNavigation,
    suggestions,
    setSelected: options.setSelected,
    acceptSelectedSuggestion: options.acceptSelectedSuggestion
  })) return
  if (input && !key.meta && !key.ctrl) {
    options.insert(input)
  }
}

function isIgnoredNavigationInput(key: TextBufferKey) {
  return key.pageUp || key.pageDown || key.mouse || key.wheelUp || key.wheelDown || ((key.meta || key.shift) && (key.upArrow || key.downArrow))
}
