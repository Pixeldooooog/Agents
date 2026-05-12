type GraphemeSegmenter = {
  segment(value: string): Iterable<{segment: string}>
}

const Segmenter = (Intl as typeof Intl & {
  Segmenter?: new (locale?: string, options?: {granularity: 'grapheme' | 'word'}) => GraphemeSegmenter | WordSegmenter
}).Segmenter

type WordSegmenter = {
  segment(value: string): Iterable<{segment: string; index: number; isWordLike?: boolean}>
}

const graphemeSegmenter = Segmenter ? new Segmenter(undefined, {granularity: 'grapheme'}) as GraphemeSegmenter : undefined
const wordSegmenter = Segmenter ? new Segmenter(undefined, {granularity: 'word'}) as WordSegmenter : undefined

export function graphemes(value: string): string[] {
  if (!value) return []
  if (!graphemeSegmenter) return Array.from(value)
  return Array.from(graphemeSegmenter.segment(value), segment => segment.segment)
}

export function charLength(value: string): number {
  return graphemes(value).length
}

export function sliceChars(value: string, start: number, end?: number): string {
  return graphemes(value).slice(start, end).join('')
}

export function charAt(value: string, index: number): string | undefined {
  return graphemes(value)[index]
}

export function insertAt(value: string, cursor: number, text: string): string {
  const chars = graphemes(value)
  chars.splice(cursor, 0, ...graphemes(text))
  return chars.join('')
}

export function removeBefore(value: string, cursor: number): string {
  const chars = graphemes(value)
  chars.splice(Math.max(0, cursor - 1), 1)
  return chars.join('')
}

export function removeAt(value: string, cursor: number): string {
  const chars = graphemes(value)
  chars.splice(cursor, 1)
  return chars.join('')
}

export function dropLastChar(value: string): string {
  return graphemes(value).slice(0, -1).join('')
}

export function previousWordBoundary(value: string, cursor: number): number {
  const segmented = previousSegmentedWordBoundary(value, cursor)
  if (segmented !== undefined) return segmented
  const chars = graphemes(value)
  let index = Math.min(cursor, chars.length)
  while (index > 0 && /\s/.test(chars[index - 1] ?? '')) index -= 1
  while (index > 0 && !/\s/.test(chars[index - 1] ?? '')) index -= 1
  return index
}

export function nextWordBoundary(value: string, cursor: number): number {
  const segmented = nextSegmentedWordBoundary(value, cursor)
  if (segmented !== undefined) return segmented
  const chars = graphemes(value)
  let index = Math.min(cursor, chars.length)
  while (index < chars.length && /\s/.test(chars[index] ?? '')) index += 1
  while (index < chars.length && !/\s/.test(chars[index] ?? '')) index += 1
  return index
}

function previousSegmentedWordBoundary(value: string, cursor: number): number | undefined {
  const words = wordBoundaries(value)
  if (!words.length) return undefined
  const point = Math.min(cursor, charLength(value))
  let previous = 0
  for (const word of words) {
    if (point > word.start && point <= word.end) return word.start
    if (word.start < point) previous = word.start
  }
  return previous
}

function nextSegmentedWordBoundary(value: string, cursor: number): number | undefined {
  const words = wordBoundaries(value)
  if (!words.length) return undefined
  const point = Math.min(cursor, charLength(value))
  for (const word of words) {
    if (point >= word.start && point < word.end) return word.end
    if (word.start > point) return word.end
  }
  return charLength(value)
}

function wordBoundaries(value: string): Array<{start: number; end: number}> {
  if (!wordSegmenter || !value) return []
  return Array.from(wordSegmenter.segment(value))
    .filter(segment => segment.isWordLike)
    .map(segment => {
      const start = codeUnitToGraphemeIndex(value, segment.index)
      const end = codeUnitToGraphemeIndex(value, segment.index + segment.segment.length)
      return {start, end}
    })
    .filter(boundary => boundary.end > boundary.start)
}

function codeUnitToGraphemeIndex(value: string, offset: number): number {
  const parts = graphemes(value)
  let codeUnits = 0
  for (let index = 0; index < parts.length; index += 1) {
    if (offset <= codeUnits) return index
    codeUnits += parts[index]?.length ?? 0
    if (offset <= codeUnits) return index + 1
  }
  return parts.length
}

export function isBackspaceInput(input: string, key: {backspace?: boolean; delete?: boolean}, rawInput = ''): boolean {
  if (key.backspace || input === '\u007F' || input === '\b') return true
  if (key.delete && rawInput && !isDeleteSequence(rawInput)) return true
  return Boolean(key.delete && !rawInput)
}

export function isDeleteInput(input: string, key: {delete?: boolean}, rawInput = ''): boolean {
  return Boolean(isDeleteSequence(rawInput) || input === '\u001B[3~' || (key.delete && isDeleteSequence(rawInput)))
}

function isDeleteSequence(value: string): boolean {
  return value === '\u001B[3~' || /^\u001B\[3[;:].*[~u]$/.test(value)
}

export function displayWidth(value: string): number {
  return graphemes(value).reduce((width, char) => width + graphemeWidth(char), 0)
}

export function padDisplayEnd(value: string, targetWidth: number): string {
  return value + ' '.repeat(Math.max(0, targetWidth - displayWidth(value)))
}

function graphemeWidth(value: string): number {
  const codePoint = value.codePointAt(0)
  if (!codePoint) return 0
  if (isCombiningMark(codePoint)) return 0
  return isFullWidthCodePoint(codePoint) ? 2 : 1
}

function isCombiningMark(codePoint: number): boolean {
  return (
    (codePoint >= 0x0300 && codePoint <= 0x036f) ||
    (codePoint >= 0x1ab0 && codePoint <= 0x1aff) ||
    (codePoint >= 0x1dc0 && codePoint <= 0x1dff) ||
    (codePoint >= 0x20d0 && codePoint <= 0x20ff) ||
    (codePoint >= 0xfe20 && codePoint <= 0xfe2f)
  )
}

function isFullWidthCodePoint(codePoint: number): boolean {
  return (
    (codePoint >= 0x1100 && codePoint <= 0x115f) ||
    codePoint === 0x2329 ||
    codePoint === 0x232a ||
    (codePoint >= 0x2e80 && codePoint <= 0xa4cf && codePoint !== 0x303f) ||
    (codePoint >= 0xac00 && codePoint <= 0xd7a3) ||
    (codePoint >= 0xf900 && codePoint <= 0xfaff) ||
    (codePoint >= 0xfe10 && codePoint <= 0xfe19) ||
    (codePoint >= 0xfe30 && codePoint <= 0xfe6f) ||
    (codePoint >= 0xff00 && codePoint <= 0xff60) ||
    (codePoint >= 0xffe0 && codePoint <= 0xffe6) ||
    (codePoint >= 0x1f300 && codePoint <= 0x1faff) ||
    (codePoint >= 0x20000 && codePoint <= 0x3fffd)
  )
}
