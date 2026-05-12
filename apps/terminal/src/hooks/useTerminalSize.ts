import {useEffect, useState} from 'react'
import {useStdout} from 'ink'

export function useTerminalSize(defaultColumns = 100, defaultRows = 30) {
  const {stdout} = useStdout()
  const [size, setSize] = useState(() => readTerminalSize(stdout, defaultColumns, defaultRows))

  useEffect(() => {
    const update = () => {
      const next = readTerminalSize(stdout, defaultColumns, defaultRows)
      setSize(current => current.columns === next.columns && current.rows === next.rows ? current : next)
    }
    stdout.on('resize', update)
    update()
    return () => {
      stdout.off('resize', update)
    }
  }, [defaultColumns, defaultRows, stdout])

  return {stdout, ...size}
}

function readTerminalSize(stdout: NodeJS.WriteStream, defaultColumns: number, defaultRows: number): {columns: number; rows: number} {
  return {
    columns: positiveNumber(stdout.columns) ?? defaultColumns,
    rows: positiveNumber(stdout.rows) ?? defaultRows
  }
}

function positiveNumber(value: number | undefined): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : undefined
}
