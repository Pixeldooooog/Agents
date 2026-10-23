import {useEffect} from 'react'
import type {TerminalHostClient} from '../protocol/terminalHostClient.js'
import type {TranscriptItem} from '../components/MessageList.js'
import type {useCommandRunner} from '../hooks/useCommandRunner.js'
import type {useRuntimeEventSink} from '../hooks/useRuntimeEventSink.js'
import {handleTerminalHostEvent} from './terminalHostEventHandlers.js'
import type {useTerminalAppState} from './useTerminalAppState.js'

type TerminalHostLifecycleOptions = {
  terminalHost: TerminalHostClient
  appState: ReturnType<typeof useTerminalAppState>
  runtimeEvents: ReturnType<typeof useRuntimeEventSink>
  inputQueue: ReturnType<typeof useCommandRunner>['inputQueue']
  append: (item: TranscriptItem) => void
  followLatest: () => void
  exit: () => void
}

export function useTerminalHostLifecycle({
  terminalHost,
  appState,
  runtimeEvents,
  inputQueue,
  append,
  followLatest,
  exit
}: TerminalHostLifecycleOptions) {
  useEffect(() => {
    appState.runtimeRef.current = appState.runtime
  }, [appState.runtime, appState.runtimeRef])

  useEffect(() => {
    const unsubscribe = terminalHost.onEvent(event => {
      handleTerminalHostEvent(event, {
        exit,
        runtimeEvents,
        inputQueue,
        append,
        followLatest,
        ...appState
      })
    })
    terminalHost.start()
    return () => {
      unsubscribe()
      terminalHost.stop()
    }
  }, [terminalHost])
}
