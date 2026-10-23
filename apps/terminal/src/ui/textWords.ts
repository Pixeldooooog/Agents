import {charLength, codeUnitToGraphemeIndex, graphemes} from './textGraphemes.js'

type WordSegmenter = {
  segment(value: string): Iterable<{segment: string; index: number; isWordLike?: boolean}>
}

const Segmenter = (Intl as typeof Intl & {
  Segmenter?: new (locale?: string, options?: {granularity: 'word'}) => WordSegmenter
}).Segmenter

const wordSegmenter = Segmenter ? new Segmenter(undefined, {granularity: 'word'}) as WordSegmenter : undefined

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
