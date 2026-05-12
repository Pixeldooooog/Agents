import {useMemo, useState} from 'react'
import {charLength, removeBefore} from '../ui/textBuffer.js'

export type HistorySearchState = {
  active: boolean
  query: string
  match?: string
  failed: boolean
}

export function useHistorySearch(history?: string[]) {
  const [active, setActive] = useState(false)
  const [query, setQuery] = useState('')
  const [matchIndex, setMatchIndex] = useState(0)
  const matches = useMemo(() => {
    if (!history?.length) return []
    const normalized = query.trim().toLowerCase()
    const source = [...history].reverse()
    return normalized ? source.filter(item => item.toLowerCase().includes(normalized)) : source
  }, [history, query])
  const match = matches[Math.min(matchIndex, Math.max(0, matches.length - 1))]

  function open() {
    setActive(true)
    setQuery('')
    setMatchIndex(0)
  }

  function close() {
    setActive(false)
    setQuery('')
    setMatchIndex(0)
  }

  function next() {
    if (matches.length) setMatchIndex(current => (current + 1) % matches.length)
  }

  function previous() {
    if (matches.length) setMatchIndex(current => (current - 1 + matches.length) % matches.length)
  }

  function append(text: string) {
    setQuery(current => current + text)
    setMatchIndex(0)
  }

  function backspace() {
    setQuery(current => removeBefore(current, charLength(current)))
    setMatchIndex(0)
  }

  return {
    active,
    match,
    open,
    close,
    next,
    previous,
    append,
    backspace,
    state: {
      active,
      query,
      match,
      failed: Boolean(query && !matches.length)
    } satisfies HistorySearchState
  }
}
