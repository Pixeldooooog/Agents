import {useRef, useState} from 'react'

export type QueuedInput = {
  value: string
  display: string
}

export function useInputQueue(onRun: (value: string, displayValue?: string) => void) {
  const [items, setItems] = useState<QueuedInput[]>([])
  const itemsRef = useRef<QueuedInput[]>([])
  const onRunRef = useRef(onRun)
  onRunRef.current = onRun

  function enqueue(value: string, display = value) {
    setItems(current => {
      const next = [...current, {value, display}]
      itemsRef.current = next
      return next
    })
  }

  function runNext() {
    setItems(current => {
      const [next, ...rest] = current
      itemsRef.current = rest
      if (next) queueMicrotask(() => onRunRef.current(next.value, next.display))
      return rest
    })
  }

  function clear(): number {
    const count = itemsRef.current.length
    itemsRef.current = []
    setItems([])
    return count
  }

  return {items, enqueue, runNext, clear}
}
