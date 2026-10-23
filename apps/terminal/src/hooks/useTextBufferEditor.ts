import {useRef, useState, type SetStateAction} from 'react'
import {
  charLength,
  insertAt,
  nextWordBoundary,
  previousWordBoundary,
  removeAt,
  removeBefore,
  sliceChars
} from '../ui/textBuffer.js'

export function useTextBufferEditor({onEdit}: {onEdit: () => void}) {
  const [value, setValue] = useState('')
  const [cursor, setCursor] = useState(0)
  const valueRef = useRef(value)
  const cursorRef = useRef(cursor)

  function insert(text: string) {
    const currentValue = valueRef.current
    const currentCursor = cursorRef.current
    applyEdit(insertAt(currentValue, currentCursor, text), currentCursor + charLength(text))
  }

  function replace(text: string) {
    applyEdit(text, charLength(text))
  }

  function replaceRange(start: number, end: number, text: string) {
    const currentValue = valueRef.current
    applyEdit(`${sliceChars(currentValue, 0, start)}${text}${sliceChars(currentValue, end)}`, start + charLength(text))
  }

  function removeBeforeCursor() {
    const currentValue = valueRef.current
    const currentCursor = cursorRef.current
    if (currentCursor <= 0) return
    applyEdit(removeBefore(currentValue, currentCursor), currentCursor - 1)
  }

  function removeAfterCursor() {
    const currentValue = valueRef.current
    const currentCursor = cursorRef.current
    if (currentCursor >= charLength(currentValue)) return
    applyEdit(removeAt(currentValue, currentCursor), currentCursor)
  }

  function removeWordBeforeCursor() {
    const currentValue = valueRef.current
    const currentCursor = cursorRef.current
    if (currentCursor <= 0) return
    const start = previousWordBoundary(currentValue, currentCursor)
    applyEdit(`${sliceChars(currentValue, 0, start)}${sliceChars(currentValue, currentCursor)}`, start)
  }

  function removeWordAfterCursor() {
    const currentValue = valueRef.current
    const currentCursor = cursorRef.current
    if (currentCursor >= charLength(currentValue)) return
    const end = nextWordBoundary(currentValue, currentCursor)
    applyEdit(`${sliceChars(currentValue, 0, currentCursor)}${sliceChars(currentValue, end)}`, currentCursor)
  }

  function keepTextAfterCursor() {
    applyEdit(sliceChars(valueRef.current, cursorRef.current), 0)
  }

  function keepTextBeforeCursor() {
    const currentCursor = cursorRef.current
    applyEdit(sliceChars(valueRef.current, 0, currentCursor), currentCursor)
  }

  function resetValue() {
    commit('', 0)
  }

  function applyEdit(nextValue: string, nextCursor: number) {
    commit(nextValue, nextCursor)
    onEdit()
  }

  function commit(nextValue: string, nextCursor: number) {
    const clampedCursor = clampCursor(nextValue, nextCursor)
    valueRef.current = nextValue
    cursorRef.current = clampedCursor
    setValue(nextValue)
    setCursor(clampedCursor)
  }

  function commitCursor(nextCursor: number) {
    const clampedCursor = clampCursor(valueRef.current, nextCursor)
    cursorRef.current = clampedCursor
    setCursor(clampedCursor)
  }

  function setCommittedValue(action: SetStateAction<string>) {
    setValue(current => {
      const next = typeof action === 'function' ? action(current) : action
      valueRef.current = next
      return next
    })
  }

  function setCommittedCursor(action: SetStateAction<number>) {
    setCursor(current => {
      const raw = typeof action === 'function' ? action(current) : action
      const next = clampCursor(valueRef.current, raw)
      cursorRef.current = next
      return next
    })
  }

  function clampCursor(text: string, point: number) {
    return Math.max(0, Math.min(charLength(text), point))
  }

  return {
    value,
    cursor,
    valueRef,
    cursorRef,
    insert,
    replace,
    replaceRange,
    removeBeforeCursor,
    removeAfterCursor,
    removeWordBeforeCursor,
    removeWordAfterCursor,
    keepTextAfterCursor,
    keepTextBeforeCursor,
    resetValue,
    commitCursor,
    setCommittedValue,
    setCommittedCursor
  }
}
