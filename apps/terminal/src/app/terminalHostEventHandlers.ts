import type {Dispatch, MutableRefObject, SetStateAction} from 'react'
import type {TranscriptItem} from '../components/MessageList.js'
import type {PendingApproval, ModelProfile, RuntimeInfo, SessionRecord, TerminalHostEvent, WorkspaceInfo} from '../protocol/terminalHostProtocol.js'
import {runtimeLabel} from '../ui/format.js'
import {formatDuration} from '../ui/runtimeEvents.js'
import {sessionTableRows} from '../ui/sessionRows.js'
import {terminalCommands, type CommandDef} from '../ui/commands.js'
import type {useCommandRunner} from '../hooks/useCommandRunner.js'
import type {useRuntimeEventSink} from '../hooks/useRuntimeEventSink.js'
import {handleSimpleTerminalHostEvent} from './terminalHostSimpleEvents.js'

export type TerminalHostEventContext = {
  exit: () => void
  runtimeRef: MutableRefObject<RuntimeInfo | undefined>
  activeRunId: MutableRefObject<string>
  hasInterruptibleToolInProgress: MutableRefObject<boolean>
  turnStartedAt: MutableRefObject<number>
  modelPickerRequested: MutableRefObject<boolean>
  sessionPickerRequested: MutableRefObject<boolean>
  suppressNextModelProfiles: MutableRefObject<boolean>
  runtimeEvents: ReturnType<typeof useRuntimeEventSink>
  inputQueue: ReturnType<typeof useCommandRunner>['inputQueue']
  append: (item: TranscriptItem) => void
  followLatest: () => void
  setRuntime: Dispatch<SetStateAction<RuntimeInfo | undefined>>
  setWorkspace: Dispatch<SetStateAction<WorkspaceInfo | undefined>>
  setProfile: Dispatch<SetStateAction<string>>
  setPermission: Dispatch<SetStateAction<string>>
  setSandbox: Dispatch<SetStateAction<string>>
  setToolCount: Dispatch<SetStateAction<number>>
  setItems: Dispatch<SetStateAction<TranscriptItem[]>>
  setBusy: Dispatch<SetStateAction<boolean>>
  setCommands: Dispatch<SetStateAction<CommandDef[]>>
  setModelProfiles: Dispatch<SetStateAction<ModelProfile[]>>
  setModelPicker: Dispatch<SetStateAction<ModelProfile[] | null>>
  setSessionPicker: Dispatch<SetStateAction<SessionRecord[] | null>>
  setPendingApproval: Dispatch<SetStateAction<PendingApproval | null>>
}

export function handleTerminalHostEvent(event: TerminalHostEvent, context: TerminalHostEventContext): void {
  if (event.type === 'ready') {
    context.runtimeRef.current = event.runtime
    context.setRuntime(event.runtime)
    context.setWorkspace(event.workspace)
    context.setProfile(event.profile)
    context.setPermission(event.permission)
    context.setSandbox(event.sandbox)
    context.setToolCount(event.tools.length)
    context.setCommands(terminalCommands(event.commands))
    context.setModelProfiles(event.model_profiles ?? [])
    return
  }
  if (event.type === 'turn_started') {
    context.followLatest()
    context.setBusy(true)
    context.activeRunId.current = event.run_id
    context.turnStartedAt.current = Date.now()
    context.runtimeEvents.resetLiveState()
    context.append({kind: 'status', label: 'thinking', text: runtimeLabel(context.runtimeRef.current?.protocol, context.runtimeRef.current?.model)})
    return
  }
  if (event.type === 'runtime_event') {
    context.runtimeEvents.handle(event.event)
    return
  }
  if (event.type === 'turn_finished') {
    context.runtimeEvents.flushThinking()
    context.runtimeEvents.flushAssistant()
    context.setBusy(false)
    context.activeRunId.current = ''
    context.hasInterruptibleToolInProgress.current = false
    if (event.status === 'waiting_approval') {
      context.append({kind: 'status', label: 'approval', text: 'waiting for your decision', level: 'warning'})
    } else {
      context.append({
        kind: 'status',
        label: turnFinishedLabel(event.status, event.reason),
        text: context.turnStartedAt.current ? `${event.status === 'failed' ? 'after ' : ''}${formatDuration(Date.now() - context.turnStartedAt.current)}` : undefined,
        level: event.status === 'failed' ? 'error' : 'info'
      })
      context.inputQueue.runNext()
    }
    return
  }
  if (event.type === 'model_profiles') {
    context.setModelProfiles(event.profiles)
    if (context.suppressNextModelProfiles.current) {
      context.suppressNextModelProfiles.current = false
      return
    }
    if (context.modelPickerRequested.current) {
      context.modelPickerRequested.current = false
      context.setModelPicker(event.profiles)
    } else {
      context.append({kind: 'models', profiles: event.profiles})
    }
    return
  }
  if (event.type === 'sessions') {
    if (context.sessionPickerRequested.current) {
      context.sessionPickerRequested.current = false
      context.setSessionPicker(event.sessions)
    } else {
      context.append({
        kind: 'table',
        title: 'Sessions',
        rows: sessionTableRows(event.sessions)
      })
    }
    return
  }
  if (event.type === 'model_switched') {
    context.runtimeRef.current = event.runtime
    context.setRuntime(event.runtime)
    context.append({kind: 'status', label: 'model', text: `switched to ${event.profile} · ${event.runtime.model}`, level: 'success'})
    return
  }
  if (event.type === 'runtime') {
    context.runtimeRef.current = event.runtime
    context.setRuntime(event.runtime)
    context.append({kind: 'status', label: 'runtime', text: runtimeLabel(event.runtime.protocol, event.runtime.model), level: 'success'})
    return
  }

  handleSimpleTerminalHostEvent(event, context)
}

function turnFinishedLabel(status: string, reason: string | undefined): string {
  if (status === 'completed') return 'done'
  if (status === 'failed') return 'stopped'
  if (status === 'cancelled' && reason === 'interrupt') return 'interrupted'
  return status
}
