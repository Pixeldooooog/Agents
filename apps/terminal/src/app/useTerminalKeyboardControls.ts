import type {TranscriptItem} from '../components/MessageList.js'
import {useSafeInput} from '../hooks/useSafeInput.js'

type TerminalKeyboardControlOptions = {
  isActive: boolean
  items: TranscriptItem[]
  canScrollTranscript: boolean
  pageScrollRows: number
  wheelScrollRows: number
  toggleCollapsed: () => void
  cycleToolDetails: (items: TranscriptItem[]) => void
  scrollTranscript: (delta: number) => void
}

export function useTerminalKeyboardControls(options: TerminalKeyboardControlOptions) {
  useSafeInput((input, key) => {
    if (key.ctrl && input === 'o') {
      options.toggleCollapsed()
      return
    }
    if (key.ctrl && input === 't') {
      options.cycleToolDetails(options.items)
      return
    }
    if (options.canScrollTranscript && key.pageUp) {
      options.scrollTranscript(options.pageScrollRows)
      return
    }
    if (options.canScrollTranscript && key.pageDown) {
      options.scrollTranscript(-options.pageScrollRows)
      return
    }
    if (options.canScrollTranscript && key.wheelUp) {
      options.scrollTranscript(options.wheelScrollRows)
      return
    }
    if (options.canScrollTranscript && key.wheelDown) {
      options.scrollTranscript(-options.wheelScrollRows)
      return
    }
    if (options.canScrollTranscript && (key.meta || key.shift) && key.upArrow) {
      options.scrollTranscript(1)
      return
    }
    if (options.canScrollTranscript && (key.meta || key.shift) && key.downArrow) {
      options.scrollTranscript(-1)
    }
  }, {isActive: options.isActive})
}
