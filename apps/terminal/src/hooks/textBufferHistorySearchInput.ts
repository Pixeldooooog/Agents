import {isBackspaceInput, isDeleteInput} from '../ui/textBuffer.js'
import {isReturnInput} from './textBufferInput.js'
import type {TextBufferKey} from './textBufferTypes.js'
import type {useHistorySearch} from './useHistorySearch.js'

type HistorySearchController = ReturnType<typeof useHistorySearch>

export function handleTextBufferHistorySearchInput({
  input,
  key,
  rawInput,
  historySearch,
  onSubmit,
  reset,
  acceptHistorySearch
}: {
  input: string
  key: TextBufferKey
  rawInput: string
  historySearch: HistorySearchController
  onSubmit: (value: string, displayValue?: string) => void
  reset: () => void
  acceptHistorySearch: () => void
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
  if (isBackspaceInput(input, key, rawInput) || isDeleteInput(input, key, rawInput)) {
    historySearch.backspace()
    return
  }
  if (input && !key.meta && !key.ctrl) {
    historySearch.append(input)
  }
}
