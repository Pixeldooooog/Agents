import {
  PASTE_TRUNCATION_THRESHOLD,
  bracketedPasteText,
  isBracketedPasteEnd,
  isBracketedPasteStart,
  lineCount,
  normalizePastedText
} from './textBufferInput.js'

type InsertText = (text: string, rawInput?: string) => void

export function createPasteBuffer() {
  const pasteRefs = new Map<string, string>()
  let bracketedPasteBuffer: string | null = null
  let nextPasteId = 1

  function displayTextForInput(text: string): string {
    if (text.length <= PASTE_TRUNCATION_THRESHOLD) return text
    const id = nextPasteId++
    const reference = `[...Pasted text #${id} +${lineCount(text)} lines...]`
    pasteRefs.set(reference, text)
    return reference
  }

  function expandPasteRefs(text: string): string {
    let expanded = text
    for (const [reference, content] of pasteRefs) {
      expanded = expanded.split(reference).join(content)
    }
    return expanded
  }

  function clear() {
    pasteRefs.clear()
    bracketedPasteBuffer = null
  }

  function handleBracketedPasteEvent(input: string, rawInput: string, insertText: InsertText): boolean {
    const fullPaste = bracketedPasteText(rawInput)
    if (fullPaste !== undefined) {
      insertText(fullPaste, '')
      return true
    }
    if (isBracketedPasteStart(input, rawInput)) {
      bracketedPasteBuffer = ''
      return true
    }
    if (bracketedPasteBuffer === null) return false
    if (isBracketedPasteEnd(input, rawInput)) {
      const pasted = normalizePastedText(bracketedPasteBuffer)
      bracketedPasteBuffer = null
      insertText(pasted, '')
      return true
    }
    bracketedPasteBuffer += rawInput || input
    return true
  }

  return {displayTextForInput, expandPasteRefs, clear, handleBracketedPasteEvent}
}
