import type {Dispatch, SetStateAction} from 'react'
import type {BridgeClient} from '../protocol/bridge.js'
import type {TranscriptItem} from '../components/MessageList.js'
import {classifyInputCommand, commandHelpRows, isCommandAvailableWhileBusy, type CommandDef} from '../ui/commands.js'
import {useInputQueue} from './useInputQueue.js'

type MutableRef<T> = {
  current: T
}

type CommandRunnerOptions = {
  busy: boolean
  bridge: BridgeClient
  commands: CommandDef[]
  activeRunId: MutableRef<string>
  modelPickerRequested: MutableRef<boolean>
  sessionPickerRequested: MutableRef<boolean>
  suppressNextModelProfiles: MutableRef<boolean>
  append: (item: TranscriptItem) => void
  addInputHistory: (value: string) => void
  setItems: Dispatch<SetStateAction<TranscriptItem[]>>
  setCollapsed: Dispatch<SetStateAction<boolean>>
  onInputRun?: () => void
  stop: () => void
}

export function useCommandRunner({
  busy,
  bridge,
  commands,
  activeRunId,
  modelPickerRequested,
  sessionPickerRequested,
  suppressNextModelProfiles,
  append,
  addInputHistory,
  setItems,
  setCollapsed,
  onInputRun,
  stop
}: CommandRunnerOptions) {
  const inputQueue = useInputQueue(runInput)

  function submit(value: string, displayValue = value) {
    const commandText = displayValue === value ? value : displayValue
    if (displayValue === value) addInputHistory(value)
    if (busy && !commandText.startsWith('/')) {
      inputQueue.enqueue(value, displayValue)
      append({kind: 'status', label: 'queued', text: displayValue})
      return
    }
    runInput(value, displayValue)
  }

  function openModelPicker() {
    if (busy) {
      append({kind: 'status', label: 'busy', text: 'run active; use /cancel before switching models', level: 'warning'})
      return
    }
    modelPickerRequested.current = true
    bridge.send({type: 'slash', text: '/model'})
  }

  function runInput(value: string, displayValue = value) {
    const commandText = displayValue === value ? value : displayValue
    if (busy && commandText.startsWith('/') && !isCommandAvailableWhileBusy(commandText, commands)) {
      append({kind: 'status', label: 'busy', text: 'run active; use /cancel to interrupt before running that command', level: 'warning'})
      return
    }
    onInputRun?.()
    append({kind: 'user', text: displayValue})
    switch (classifyInputCommand(commandText)) {
      case 'exit':
        stop()
        return
      case 'help':
        append({kind: 'table', title: 'Commands', rows: commandHelpRows(commands)})
        return
      case 'model_picker':
        modelPickerRequested.current = true
        bridge.send({type: 'slash', text: value})
        return
      case 'model_switch':
        suppressNextModelProfiles.current = true
        bridge.send({type: 'slash', text: value})
        return
      case 'resume_picker':
        sessionPickerRequested.current = true
        bridge.send({type: 'slash', text: '/sessions'})
        return
      case 'fold':
        setCollapsed(true)
        append({kind: 'status', label: 'fold', text: 'long blocks collapsed'})
        return
      case 'unfold':
        setCollapsed(false)
        append({kind: 'status', label: 'unfold', text: 'long blocks expanded'})
        return
      case 'queue':
        append({
          kind: 'table',
          title: 'Queued Messages',
          rows: inputQueue.items.length ? inputQueue.items.map((item, index) => [String(index + 1), item.display]) : [['queue', 'empty']]
        })
        return
      case 'cancel': {
        const count = inputQueue.clear()
        if (busy) {
          bridge.send({type: 'cancel', run_id: activeRunId.current || undefined})
          append({kind: 'status', label: 'interrupt', text: count ? `requested · cleared ${count} queued message${count === 1 ? '' : 's'}` : 'requested'})
          return
        }
        append({kind: 'status', label: 'queue', text: count ? `cleared ${count} queued message${count === 1 ? '' : 's'}` : 'empty'})
        return
      }
      case 'clear':
        setItems([])
        bridge.send({type: 'slash', text: value})
        return
      case 'slash':
        bridge.send({type: 'slash', text: commandText})
        return
      case 'message':
        bridge.send({type: 'user_message', text: value})
        return
    }
  }

  function interruptActiveRun(): boolean {
    if (!busy) return false
    runInput('/cancel')
    return true
  }

  function interruptOrStop(): boolean {
    if (interruptActiveRun()) return true
    stop()
    return false
  }

  return {inputQueue, submit, runInput, openModelPicker, interruptActiveRun, interruptOrStop}
}
