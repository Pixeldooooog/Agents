import {useRef, useState, type Dispatch, type SetStateAction} from 'react'
import type {RuntimeEvent} from '../protocol/terminalHostProtocol.js'
import type {TranscriptItem} from '../components/MessageList.js'
import {argsFromPayload, stringifyToolContent, summarizeToolResult, toolIds, toolKey} from '../ui/runtimeEvents.js'

export function useToolTimeline(setItems: Dispatch<SetStateAction<TranscriptItem[]>>) {
  const [selectedToolId, setSelectedToolId] = useState<string | undefined>(undefined)
  const [expandedToolIds, setExpandedToolIds] = useState<Set<string>>(new Set())
  const indexes = useRef(new Map<string, number>())
  const startTimes = useRef(new Map<string, number>())

  function reset() {
    indexes.current.clear()
    startTimes.current.clear()
    setSelectedToolId(undefined)
    setExpandedToolIds(new Set())
  }

  function start(event: RuntimeEvent, payload: Record<string, unknown>) {
    const args = argsFromPayload(payload)
    const item: TranscriptItem = {kind: 'tool', name: event.name ?? 'tool', args}
    setItems(current => {
      const key = toolKey(event, payload)
      item.id = key
      indexes.current.set(key, current.length)
      startTimes.current.set(key, Date.now())
      setSelectedToolId(key)
      return [...current, item]
    })
  }

  function finish(event: RuntimeEvent, payload: Record<string, unknown>) {
    const key = toolKey(event, payload)
    const result = summarizeToolResult(event.name ?? '', payload.content, Boolean(payload.is_error))
    const detail = stringifyToolContent(payload.content)
    const startedAt = startTimes.current.get(key)
    const durationMs = startedAt ? Date.now() - startedAt : undefined
    setItems(current => {
      const next = [...current]
      const index = indexes.current.get(key)
      if (index !== undefined && next[index]?.kind === 'tool') {
        next[index] = {...next[index], id: key, result, detail, error: Boolean(payload.is_error), durationMs} as TranscriptItem
      } else {
        next.push({kind: 'tool', id: key, name: event.name ?? 'tool', result, detail, error: Boolean(payload.is_error), durationMs})
      }
      return next
    })
  }

  function focusNext(items: TranscriptItem[]) {
    const tools = toolIds(items)
    if (!tools.length) return
    const current = selectedToolId ? tools.indexOf(selectedToolId) : -1
    setSelectedToolId(tools[(current + 1 + tools.length) % tools.length])
  }

  function cycleDetails(items: TranscriptItem[]) {
    const tools = toolIds(items)
    if (!tools.length) return
    const current = selectedToolId ? tools.indexOf(selectedToolId) : -1
    const currentId = current >= 0 ? tools[current] : tools[0]
    if (!currentId) return
    if (!expandedToolIds.has(currentId)) {
      setSelectedToolId(currentId)
      setExpandedToolIds(nextSetWith(currentId))
      return
    }
    const nextId = tools[(current + 1 + tools.length) % tools.length]
    setSelectedToolId(nextId)
    if (nextId) setExpandedToolIds(nextSetWith(nextId))
  }

  function toggle(id = selectedToolId) {
    if (!id) return
    setExpandedToolIds(current => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function nextSetWith(id: string) {
    return (current: Set<string>) => new Set([...current, id])
  }

  return {selectedToolId, expandedToolIds, reset, start, finish, focusNext, cycleDetails, toggle}
}
