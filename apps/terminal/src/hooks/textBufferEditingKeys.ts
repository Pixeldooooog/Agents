import {charLength, isBackspaceInput, isDeleteInput, nextWordBoundary, previousWordBoundary} from '../ui/textBuffer.js'
import type {TextBufferKey} from './textBufferTypes.js'
import type {useTextBufferEditor} from './useTextBufferEditor.js'

type TextBufferEditor = ReturnType<typeof useTextBufferEditor>

type TextBufferEditingKeyOptions = {
  input: string
  key: TextBufferKey
  rawInput: string
  currentValue: string
  currentCursor: number
  editor: TextBufferEditor
}

export function handleTextBufferEditingKey({
  input,
  key,
  rawInput,
  currentValue,
  currentCursor,
  editor
}: TextBufferEditingKeyOptions): boolean {
  if (key.meta && isBackspaceInput(input, key, rawInput)) {
    editor.removeWordBeforeCursor()
    return true
  }
  if (isBackspaceInput(input, key, rawInput)) {
    editor.removeBeforeCursor()
    return true
  }
  if ((key.meta || key.ctrl) && isDeleteInput(input, key, rawInput)) {
    editor.removeWordAfterCursor()
    return true
  }
  if (isDeleteInput(input, key, rawInput)) {
    editor.removeAfterCursor()
    return true
  }
  if (key.leftArrow && (key.ctrl || key.meta)) {
    editor.commitCursor(previousWordBoundary(currentValue, currentCursor))
    return true
  }
  if (key.rightArrow && (key.ctrl || key.meta)) {
    editor.commitCursor(nextWordBoundary(currentValue, currentCursor))
    return true
  }
  if (key.home) {
    editor.commitCursor(0)
    return true
  }
  if (key.end) {
    editor.commitCursor(charLength(currentValue))
    return true
  }
  if (key.leftArrow) {
    editor.commitCursor(currentCursor - 1)
    return true
  }
  if (key.rightArrow) {
    editor.commitCursor(currentCursor + 1)
    return true
  }
  if (key.meta && input === 'b') {
    editor.commitCursor(previousWordBoundary(currentValue, currentCursor))
    return true
  }
  if (key.meta && input === 'f') {
    editor.commitCursor(nextWordBoundary(currentValue, currentCursor))
    return true
  }
  if (key.meta && input === 'd') {
    editor.removeWordAfterCursor()
    return true
  }
  if (key.ctrl && input === 'b') {
    editor.commitCursor(currentCursor - 1)
    return true
  }
  if (key.ctrl && input === 'f') {
    editor.commitCursor(currentCursor + 1)
    return true
  }
  if (key.ctrl && input === 'a') {
    editor.commitCursor(0)
    return true
  }
  if (key.ctrl && input === 'e') {
    editor.commitCursor(charLength(currentValue))
    return true
  }
  if (key.ctrl && input === 'w') {
    editor.removeWordBeforeCursor()
    return true
  }
  if (key.ctrl && input === 'u') {
    editor.keepTextAfterCursor()
    return true
  }
  if (key.ctrl && input === 'k') {
    editor.keepTextBeforeCursor()
    return true
  }
  return false
}
