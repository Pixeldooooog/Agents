export const PASTE_TRUNCATION_THRESHOLD = 10000

const ANSI_PATTERN = /(?:\u001B\[[0-?]*[ -/]*[@-~]|\u001B\][\s\S]*?(?:\u0007|\u001B\\)|\u001B[()][A-Za-z0-9])/g

export function isReturnInput(input: string, key: {return?: boolean}): boolean {
  return Boolean(key.return || input === '\r' || input === '\n')
}

export function splitBufferedReturnInput(input: string, key: {return?: boolean}): {text: string} | undefined {
  if (!input || isReturnInput(input, key)) return undefined
  const newline = trailingNewline(input)
  if (!newline) return undefined
  const text = input.slice(0, -newline.length)
  if (!text || hasLineBreak(text)) return undefined
  return {text}
}

export function lineCount(input: string): number {
  return input.split(/\r\n|\r|\n/).length
}

export function bracketedPasteText(rawInput: string): string | undefined {
  const startToken = '\u001B[200~'
  const endToken = '\u001B[201~'
  const start = rawInput.indexOf(startToken)
  const end = rawInput.lastIndexOf(endToken)
  if (start < 0 || end < start) return undefined
  return normalizePastedText(rawInput.slice(start + startToken.length, end))
}

export function isBracketedPasteStart(input: string, rawInput: string): boolean {
  return rawInput === '\u001B[200~' || input === '[200~'
}

export function isBracketedPasteEnd(input: string, rawInput: string): boolean {
  return rawInput === '\u001B[201~' || input === '[201~'
}

export function normalizeInsertedText(text: string, rawInput: string): string {
  const bracketed = bracketedPasteText(rawInput)
  if (bracketed !== undefined) return bracketed
  if (text.length <= 1 && !/[\r\n\t\u001B\u009B]/.test(text)) return text
  return normalizePastedText(text)
}

export function normalizePastedText(text: string): string {
  return text
    .replace(ANSI_PATTERN, '')
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .replaceAll('\t', '    ')
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
