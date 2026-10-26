import type {TranscriptItem} from "../components/MessageList.js"
import type {PromptOverlayState} from "../components/PromptInput.js"

export const PROMPT_BASE_ROWS = 5
export const WELCOME_ROWS = 15
export const CURSOR_STEADY_BAR = "\u001B[5 q"
export const CURSOR_RESET = "\u001B[0 q"
export const BRACKETED_PASTE_ENABLE = "\u001B[?2004h"
export const BRACKETED_PASTE_DISABLE = "\u001B[?2004l"
export const MOUSE_TRACKING_ENABLE = "\u001B[?1000h\u001B[?1006h"
export const MOUSE_TRACKING_DISABLE = "\u001B[?1006l\u001B[?1000l"

const APPROVAL_ROWS = 12
const PICKER_ROWS = 12
const PROMPT_OVERLAY_ROWS = 9

export function isFullscreenLayoutEnabled(): boolean {
  return ["1", "true", "yes", "on"].includes(String(process.env.KEVIN_TERMINAL_FULLSCREEN ?? "").toLowerCase())
}

export function withLiveTurnItems(items: TranscriptItem[], reasoning: string, assistant: string): TranscriptItem[] {
  if (!reasoning && !assistant) return items
  const liveItems: TranscriptItem[] = []
  if (reasoning) liveItems.push({kind: "thinking", text: reasoning})
  if (assistant) liveItems.push({kind: "assistant", text: assistant, live: true})
  return [...items, ...liveItems]
}

export function promptOverlayRowsForTerminal(terminalRows: number, overlay: PromptOverlayState): number {
  if (overlay.historySearch?.active) return 1
  if (terminalRows < 20) return 5
  if (terminalRows < 28) return 7
  return PROMPT_OVERLAY_ROWS
}

export function layoutRows({
  scrollableLayout,
  promptOverlay,
  terminalRows,
  promptRows,
  items,
  busy,
  terminalColumns,
  pendingApproval,
  pickerActive
}: {
  scrollableLayout: boolean
  promptOverlay: PromptOverlayState | null
  terminalRows: number
  promptRows: number
  items: TranscriptItem[]
  busy: boolean
  terminalColumns: number
  pendingApproval: boolean
  pickerActive: boolean
}): {showWelcome: boolean; overlayRows: number; messageRows: number} {
  const promptOverlayRows = scrollableLayout && promptOverlay ? promptOverlayRowsForTerminal(terminalRows, promptOverlay) : 0
  const showWelcome = items.length === 0 && !busy && terminalColumns >= 80 && (!scrollableLayout || terminalRows >= promptRows + WELCOME_ROWS + 4)
  const overlayRows = pendingApproval
    ? Math.min(APPROVAL_ROWS, Math.max(6, terminalRows - promptRows - promptOverlayRows - 1))
    : pickerActive
      ? Math.min(PICKER_ROWS, Math.max(6, terminalRows - promptRows - promptOverlayRows - 1))
      : 0
  const chromeRows = promptRows + promptOverlayRows + overlayRows + (showWelcome ? WELCOME_ROWS : 0)
  return {showWelcome, overlayRows, messageRows: Math.max(1, terminalRows - chromeRows)}
}
