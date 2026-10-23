import type {Dispatch, SetStateAction} from 'react'
import type {TextBufferKey} from './textBufferTypes.js'
import type {useHistoryNavigation} from './useHistoryNavigation.js'
import type {useTextBufferSuggestions} from './useTextBufferSuggestions.js'

type HistoryNavigationController = ReturnType<typeof useHistoryNavigation>
type SuggestionState = ReturnType<typeof useTextBufferSuggestions>

type TextBufferSelectionKeyOptions = {
  input: string
  key: TextBufferKey
  history?: string[]
  historyNavigation: HistoryNavigationController
  suggestions: SuggestionState['suggestions']
  setSelected: Dispatch<SetStateAction<number>>
  acceptSelectedSuggestion: (submitCommands: boolean) => 'none' | 'inserted' | 'submitted'
}

export function handleTextBufferSelectionKey({
  input,
  key,
  history,
  historyNavigation,
  suggestions,
  setSelected,
  acceptSelectedSuggestion
}: TextBufferSelectionKeyOptions): boolean {
  if (key.ctrl && input === 'p' && suggestions.length) {
    setSelected(current => (current - 1 + suggestions.length) % suggestions.length)
    return true
  }
  if (key.ctrl && input === 'n' && suggestions.length) {
    setSelected(current => (current + 1) % suggestions.length)
    return true
  }
  if (key.ctrl && input === 'p' && history?.length) {
    historyNavigation.show(-1)
    return true
  }
  if (key.ctrl && input === 'n' && history?.length && historyNavigation.active) {
    historyNavigation.show(1)
    return true
  }
  if (key.upArrow && suggestions.length) {
    setSelected(current => (current - 1 + suggestions.length) % suggestions.length)
    return true
  }
  if (key.downArrow && suggestions.length) {
    setSelected(current => (current + 1) % suggestions.length)
    return true
  }
  if (key.upArrow && history?.length) {
    historyNavigation.show(-1)
    return true
  }
  if (key.downArrow && history?.length && historyNavigation.active) {
    historyNavigation.show(1)
    return true
  }
  if (key.tab && suggestions.length) {
    acceptSelectedSuggestion(false)
    return true
  }
  return false
}
