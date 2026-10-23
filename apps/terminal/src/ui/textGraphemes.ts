type GraphemeSegmenter = {
  segment(value: string): Iterable<{segment: string}>
}

const Segmenter = (Intl as typeof Intl & {
  Segmenter?: new (locale?: string, options?: {granularity: 'grapheme'}) => GraphemeSegmenter
}).Segmenter

const graphemeSegmenter = Segmenter ? new Segmenter(undefined, {granularity: 'grapheme'}) as GraphemeSegmenter : undefined

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

export function codeUnitToGraphemeIndex(value: string, offset: number): number {
  const parts = graphemes(value)
  let codeUnits = 0
  for (let index = 0; index < parts.length; index += 1) {
    if (offset <= codeUnits) return index
    codeUnits += parts[index]?.length ?? 0
    if (offset <= codeUnits) return index + 1
  }
  return parts.length
}
