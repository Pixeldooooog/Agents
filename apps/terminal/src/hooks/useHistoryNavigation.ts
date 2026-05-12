import {useState, type Dispatch, type SetStateAction} from 'react'
import {charLength} from '../ui/textBuffer.js'

export function useHistoryNavigation({
  history,
  value,
  setValue,
  setCursor
}: {
  history?: string[]
  value: string
  setValue: Dispatch<SetStateAction<string>>
  setCursor: Dispatch<SetStateAction<number>>
}) {
  const [index, setIndex] = useState<number | null>(null)
  const [draft, setDraft] = useState('')

  function show(direction: -1 | 1) {
    if (!history?.length) return
    if (direction < 0) {
      const nextIndex = index === null ? history.length - 1 : Math.max(0, index - 1)
      if (index === null) setDraft(value)
      const next = history[nextIndex] ?? ''
      setIndex(nextIndex)
      setValue(next)
      setCursor(charLength(next))
      return
    }
    if (index === null) return
    const nextIndex = index + 1
    if (nextIndex >= history.length) {
      setIndex(null)
      setValue(draft)
      setCursor(charLength(draft))
      return
    }
    const next = history[nextIndex] ?? ''
    setIndex(nextIndex)
    setValue(next)
    setCursor(charLength(next))
  }

  function clear() {
    setIndex(null)
  }

  function reset() {
    setIndex(null)
    setDraft('')
  }

  return {active: index !== null, show, clear, reset}
}
