import {useEffect, useLayoutEffect, useRef} from 'react'
import {useStdin} from 'ink'
import {parseTerminalInput, splitTerminalControlEvents, type Key} from './terminalInputParser.js'

export type {Key} from './terminalInputParser.js'

type Options = {
  isActive?: boolean
}

export function useSafeInput(inputHandler: (input: string, key: Key) => void, options: Options = {}) {
  const {setRawMode, isRawModeSupported, internal_exitOnCtrlC, internal_eventEmitter} = useStdin()
  const handlerRef = useRef(inputHandler)
  const activeRef = useRef(options.isActive !== false)
  handlerRef.current = inputHandler
  activeRef.current = options.isActive !== false

  useLayoutEffect(() => {
    if (!isRawModeSupported || options.isActive === false) return
    setRawMode(true)
    return () => {
      setRawMode(false)
    }
  }, [isRawModeSupported, options.isActive, setRawMode])

  useEffect(() => {
    const handleData = (data: unknown) => {
      if (!activeRef.current) return
      const rawInput = typeof data === 'string' || Buffer.isBuffer(data) ? String(data) : String(data ?? '')
      const inputs = splitTerminalControlEvents(rawInput)
      if (inputs.length > 1) {
        for (const input of inputs) dispatchInput(input)
        return
      }
      dispatchInput(rawInput)
    }

    const dispatchInput = (rawInput: string) => {
      const {input, key} = parseTerminalInput(rawInput)
      if ((input !== 'c' || !key.ctrl) || !internal_exitOnCtrlC) {
        handlerRef.current(input, key)
      }
    }

    internal_eventEmitter.on('input', handleData)
    return () => {
      internal_eventEmitter.removeListener('input', handleData)
    }
  }, [internal_eventEmitter, internal_exitOnCtrlC])
}
