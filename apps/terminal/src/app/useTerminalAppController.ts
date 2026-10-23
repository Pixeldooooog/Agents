import {useEffect, useMemo} from 'react'
import {useApp, useStdin} from 'ink'
import {useCommandRunner} from '../hooks/useCommandRunner.js'
import {useRuntimeEventSink} from '../hooks/useRuntimeEventSink.js'
import {useTerminalSize} from '../hooks/useTerminalSize.js'
import {TerminalHostClient} from '../protocol/terminalHostClient.js'
import {nextScrollOffset} from '../ui/scroll.js'
import type {TerminalScreenProps} from './TerminalScreen.js'
import {buildTerminalViewState} from './terminalViewState.js'
import {useTerminalAppActions} from './useTerminalAppActions.js'
import {useTerminalAppState} from './useTerminalAppState.js'
import {useTerminalHostLifecycle} from './useTerminalHostLifecycle.js'
import {useTerminalKeyboardControls} from './useTerminalKeyboardControls.js'
import {useTerminalModeEffects} from './useTerminalModeEffects.js'

export type TerminalAppProps = {
  repoRoot: string
  terminalHostArgs: string[]
  terminalHostFixture?: boolean
}

export function useTerminalAppController({
  repoRoot,
  terminalHostArgs,
  terminalHostFixture
}: TerminalAppProps): TerminalScreenProps {
  const {exit} = useApp()
  const {isRawModeSupported, setRawMode} = useStdin()
  const {stdout, columns: terminalColumns, rows: terminalRows} = useTerminalSize()
  const appState = useTerminalAppState(repoRoot)
  const terminalHost = useMemo(() => {
    return new TerminalHostClient({repoRoot, args: terminalHostArgs, fixture: terminalHostFixture})
  }, [repoRoot, terminalHostArgs, terminalHostFixture])
  const actions = useTerminalAppActions({appState, terminalHost, exit})
  const runtimeEvents = useRuntimeEventSink({
    activeRunId: appState.activeRunId,
    hasInterruptibleToolInProgress: appState.hasInterruptibleToolInProgress,
    append: actions.append,
    setItems: appState.setItems,
    setPendingApproval: appState.setPendingApproval
  })
  const {assistantDraft, reasoningDraft, toolTimeline} = runtimeEvents
  const commandRunner = useCommandRunner({
    busy: appState.busy,
    terminalHost,
    commands: appState.commands,
    activeRunId: appState.activeRunId,
    hasInterruptibleToolInProgress: appState.hasInterruptibleToolInProgress,
    modelPickerRequested: appState.modelPickerRequested,
    sessionPickerRequested: appState.sessionPickerRequested,
    suppressNextModelProfiles: appState.suppressNextModelProfiles,
    append: actions.append,
    addInputHistory: appState.addInputHistory,
    setItems: appState.setItems,
    setCollapsed: appState.setCollapsed,
    onInputRun: actions.followLatest,
    stop: actions.stop
  })
  const pickerActive = Boolean(appState.modelPicker || appState.sessionPicker)
  const inputDisabledReason = appState.pendingApproval ? 'approval required · choose below' : pickerActive ? 'picker active · esc to close' : undefined
  const viewState = buildTerminalViewState({
    items: appState.items,
    busy: appState.busy,
    assistantDraft: assistantDraft.live,
    reasoningDraft: reasoningDraft.live,
    collapsed: appState.collapsed,
    expandedToolIds: toolTimeline.expandedToolIds,
    terminalColumns,
    terminalRows,
    promptOverlay: appState.promptOverlay,
    promptRows: appState.promptRows,
    pendingApprovalActive: Boolean(appState.pendingApproval),
    pickerActive,
    scrollOffset: appState.scrollOffset
  })
  const {
    transcriptLines,
    scrollableLayout,
    mouseTrackingActive,
    maxScrollOffset,
    canScrollTranscript,
    pageScrollRows,
    wheelScrollRows
  } = viewState

  useTerminalModeEffects({isRawModeSupported, mouseTrackingActive, setRawMode, stdout})

  useEffect(() => {
    const previous = appState.previousTranscriptLines.current
    appState.previousTranscriptLines.current = transcriptLines
    if (!scrollableLayout) return
    appState.setScrollOffset(current => {
      return nextScrollOffset({current, previousLines: previous, nextLines: transcriptLines, max: maxScrollOffset})
    })
  }, [appState.previousTranscriptLines, appState.setScrollOffset, scrollableLayout, maxScrollOffset, transcriptLines])

  useTerminalHostLifecycle({
    terminalHost,
    appState,
    runtimeEvents,
    inputQueue: commandRunner.inputQueue,
    append: actions.append,
    followLatest: actions.followLatest,
    exit
  })

  useTerminalKeyboardControls({
    isActive: Boolean(!appState.pendingApproval && !pickerActive && isRawModeSupported),
    items: appState.items,
    canScrollTranscript,
    pageScrollRows,
    wheelScrollRows,
    toggleCollapsed: () => appState.setCollapsed(current => !current),
    cycleToolDetails: toolTimeline.cycleDetails,
    scrollTranscript: delta => actions.scrollTranscript(delta, maxScrollOffset)
  })

  return {
    repoRoot,
    viewState,
    promptOverlay: appState.promptOverlay,
    terminalRows,
    welcome: appState,
    transcript: {
      collapsed: appState.collapsed,
      selectedToolId: toolTimeline.selectedToolId,
      expandedToolIds: toolTimeline.expandedToolIds,
      scrollOffset: appState.scrollOffset,
      terminalColumns,
      onToggleTool: toolTimeline.toggle
    },
    overlays: {
      ...appState,
      onApprovalDecision: actions.decideApproval,
      onSelectModel: actions.selectModel,
      onCancelModel: () => appState.setModelPicker(null),
      onSelectSession: actions.selectSession,
      onCancelSession: () => appState.setSessionPicker(null)
    },
    prompt: {
      ...appState,
      inputDisabledReason,
      onSubmit: commandRunner.submit,
      onExit: commandRunner.interruptOrStop,
      onCancel: commandRunner.interruptActiveRun,
      onClearScreen: actions.clearVisibleTranscript,
      onModelPicker: commandRunner.openModelPicker
    },
    onOverlayChange: appState.setPromptOverlay,
    onRowsChange: appState.setPromptRows
  }
}
