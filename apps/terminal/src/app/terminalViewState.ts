import {estimateTranscriptLines} from '../components/messageViewportLayout.js'
import type {TranscriptItem} from '../components/MessageList.js'
import type {PromptOverlayState} from '../components/PromptInput.js'
import {
  isFullscreenLayoutEnabled,
  layoutRows,
  promptOverlayRowsForTerminal,
  withLiveTurnItems
} from './terminalLayout.js'

type TerminalViewStateOptions = {
  items: TranscriptItem[]
  busy: boolean
  assistantDraft: string
  reasoningDraft: string
  collapsed: boolean
  expandedToolIds: Set<string>
  terminalColumns: number
  terminalRows: number
  promptOverlay: PromptOverlayState | null
  promptRows: number
  pendingApprovalActive: boolean
  pickerActive: boolean
  scrollOffset: number
}

export type TerminalViewState = {
  viewportItems: TranscriptItem[]
  transcriptLines: number
  scrollableLayout: boolean
  mouseTrackingActive: boolean
  showWelcome: boolean
  overlayRows: number
  messageRows: number
  maxScrollOffset: number
  canScrollTranscript: boolean
  pageScrollRows: number
  wheelScrollRows: number
  pickerRows: number
  promptOverlayRows: number
}

export function buildTerminalViewState(options: TerminalViewStateOptions): TerminalViewState {
  const modalActive = options.pendingApprovalActive || options.pickerActive
  const viewportItems = options.busy ? withLiveTurnItems(options.items, options.reasoningDraft, options.assistantDraft) : options.items
  const baseScrollableLayout = isFullscreenLayoutEnabled() || modalActive || options.scrollOffset > 0
  const baseLayout = layoutRows({
    scrollableLayout: baseScrollableLayout,
    promptOverlay: options.promptOverlay,
    terminalRows: options.terminalRows,
    promptRows: options.promptRows,
    items: options.items,
    busy: options.busy,
    terminalColumns: options.terminalColumns,
    pendingApproval: options.pendingApprovalActive,
    pickerActive: options.pickerActive
  })
  const transcriptLines = estimateTranscriptLines(viewportItems, options.collapsed, options.expandedToolIds, options.terminalColumns)
  const streamingScrollableLayout = options.busy && transcriptLines > baseLayout.messageRows
  const scrollableLayout = baseScrollableLayout || streamingScrollableLayout
  const layout = layoutRows({
    scrollableLayout,
    promptOverlay: options.promptOverlay,
    terminalRows: options.terminalRows,
    promptRows: options.promptRows,
    items: options.items,
    busy: options.busy,
    terminalColumns: options.terminalColumns,
    pendingApproval: options.pendingApprovalActive,
    pickerActive: options.pickerActive
  })
  const promptOverlayRows = scrollableLayout && options.promptOverlay ? promptOverlayRowsForTerminal(options.terminalRows, options.promptOverlay) : 0
  const maxScrollOffset = Math.max(0, transcriptLines - layout.messageRows)
  const pageScrollRows = Math.max(1, Math.floor(layout.messageRows / 2))
  return {
    viewportItems,
    transcriptLines,
    scrollableLayout,
    mouseTrackingActive: scrollableLayout || options.busy,
    showWelcome: layout.showWelcome,
    overlayRows: layout.overlayRows,
    messageRows: layout.messageRows,
    maxScrollOffset,
    canScrollTranscript: scrollableLayout || options.busy || maxScrollOffset > 0,
    pageScrollRows,
    wheelScrollRows: Math.max(1, Math.floor(pageScrollRows / 3)),
    pickerRows: Math.max(1, Math.min(6, layout.overlayRows - 6)),
    promptOverlayRows
  }
}
