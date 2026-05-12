import {mkdir, readFile, writeFile} from 'node:fs/promises'
import path from 'node:path'
import {useCallback, useEffect, useMemo, useState} from 'react'

const DEFAULT_LIMIT = 200

export function usePersistentHistory(repoRoot: string, limit = DEFAULT_LIMIT) {
  const historyPath = useMemo(() => process.env.AGENTS_TERMINAL_HISTORY_PATH || path.join(path.resolve(repoRoot), '.agents', 'terminal-history.json'), [repoRoot])
  const [history, setHistory] = useState<string[]>([])

  useEffect(() => {
    let active = true
    readHistory(historyPath, limit).then(items => {
      if (active) setHistory(items)
    })
    return () => {
      active = false
    }
  }, [historyPath, limit])

  const addHistory = useCallback((value: string) => {
    const text = value.trim()
    if (!text) return
    setHistory(current => {
      const next = dedupe([...current.filter(item => item !== text), text]).slice(-limit)
      void writeHistory(historyPath, next)
      return next
    })
  }, [historyPath, limit])

  return [history, addHistory] as const
}

async function readHistory(historyPath: string, limit: number): Promise<string[]> {
  try {
    const raw = await readFile(historyPath, 'utf8')
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return dedupe(parsed.filter(item => typeof item === 'string' && item.trim()).map(item => item.trim())).slice(-limit)
  } catch {
    return []
  }
}

async function writeHistory(historyPath: string, history: string[]): Promise<void> {
  try {
    await mkdir(path.dirname(historyPath), {recursive: true})
    await writeFile(historyPath, JSON.stringify(history, null, 2), 'utf8')
  } catch {
    // History is convenience state; terminal chat should keep working without a writable runtime directory.
  }
}

function dedupe(items: string[]): string[] {
  return [...new Set(items)]
}
