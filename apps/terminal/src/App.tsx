import React, {useEffect, useLayoutEffect, useMemo, useRef, useState} from 'react'
import {Box, useApp, useStdin} from 'ink'
import {BridgeClient} from './protocol/bridge.js'
import type {ApprovalDecision, BridgeEvent, ModelProfile, PendingApproval, RuntimeInfo, SessionRecord, ToolDefinition, WorkspaceInfo} from './protocol/types.js'
import {Welcome} from './components/Welcome.js'
import {MessageList, type TranscriptItem} from './components/MessageList.js'
import {MessageViewport, estimateTranscriptLines} from './components/MessageViewport.js'
import {PromptInput, PromptInputOverlay, type PromptOverlayState} from './components/PromptInput.js'
import {ApprovalPrompt} from './components/ApprovalPrompt.js'
import {ModelPicker} from './components/ModelPicker.js'
import {SessionPicker} from './components/SessionPicker.js'
import {runtimeLabel} from './ui/format.js'
import {useCommandRunner} from './hooks/useCommandRunner.js'
import {usePersistentHistory} from './hooks/usePersistentHistory.js'
import {useRuntimeEventSink} from './hooks/useRuntimeEventSink.js'
import {useSafeInput} from './hooks/useSafeInput.js'
import {useTerminalSize} from './hooks/useTerminalSize.js'
import {formatDuration} from './ui/runtimeEvents.js'
import {nextScrollOffset} from './ui/scroll.js'
import {sessionTableRows} from './ui/sessionRows.js'
import {transcriptFromSession} from './ui/sessionTranscript.js'
import {terminalCommands, type CommandDef} from './ui/commands.js'

const PROMPT_BASE_ROWS = 5
const APPROVAL_ROWS = 12
const PICKER_ROWS = 12
export const WELCOME_ROWS = 15
const PROMPT_OVERLAY_ROWS = 9
const CURSOR_STEADY_BAR = '\u001B[5 q'
const CURSOR_RESET = '\u001B[0 q'
const BRACKETED_PASTE_ENABLE = '\u001B[?2004h'
const BRACKETED_PASTE_DISABLE = '\u001B[?2004l'
const MOUSE_TRACKING_ENABLE = '\u001B[?1000h\u001B[?1006h'
const MOUSE_TRACKING_DISABLE = '\u001B[?1006l\u001B[?1000l'

export function App({python, repoRoot, bridgeArgs, bridgeModule}: {python: string; repoRoot: string; bridgeArgs: string[]; bridgeModule?: string}) {
  const {exit} = useApp()
  const {isRawModeSupported, setRawMode} = useStdin()
  const {stdout, columns: terminalColumns, rows: terminalRows} = useTerminalSize()
  const [runtime, setRuntime] = useState<RuntimeInfo>()
  const [workspace, setWorkspace] = useState<WorkspaceInfo>()
  const [profile, setProfile] = useState('coding')
  const [permission, setPermission] = useState('guarded')
  const [sandbox, setSandbox] = useState('local')
  const [toolCount, setToolCount] = useState(0)
  const [items, setItems] = useState<TranscriptItem[]>([])
  const [busy, setBusy] = useState(false)
  const [collapsed, setCollapsed] = useState(true)
  const [scrollOffset, setScrollOffset] = useState(0)
  const [inputHistory, addInputHistory] = usePersistentHistory(repoRoot)
  const [modelProfiles, setModelProfiles] = useState<ModelProfile[]>([])
  const [commands, setCommands] = useState<CommandDef[]>(() => terminalCommands())
  const [modelPicker, setModelPicker] = useState<ModelProfile[] | null>(null)
  const [sessionPicker, setSessionPicker] = useState<SessionRecord[] | null>(null)
  const [promptOverlay, setPromptOverlay] = useState<PromptOverlayState | null>(null)
  const [promptRows, setPromptRows] = useState(PROMPT_BASE_ROWS)
  const [pendingApproval, setPendingApproval] = useState<PendingApproval | null>(null)
  const runtimeRef = useRef<RuntimeInfo | undefined>(undefined)
  const activeRunId = useRef('')
  const turnStartedAt = useRef(0)
  const previousTranscriptLines = useRef(0)
  const modelPickerRequested = useRef(false)
  const sessionPickerRequested = useRef(false)
  const suppressNextModelProfiles = useRef(false)
  const bridge = useMemo(() => new BridgeClient({python, repoRoot, args: bridgeArgs, module: bridgeModule}), [python, repoRoot, bridgeArgs, bridgeModule])
  const runtimeEvents = useRuntimeEventSink({activeRunId, append, setItems, setPendingApproval})
  const {assistantDraft, reasoningDraft, toolTimeline} = runtimeEvents
  const commandRunner = useCommandRunner({
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
    onInputRun: followLatest,
    stop
  })
  const inputQueue = commandRunner.inputQueue
  const inputDisabledReason = pendingApproval ? 'approval required · choose below' : (modelPicker || sessionPicker) ? 'picker active · esc to close' : undefined
  const fullscreen = isFullscreenLayoutEnabled()
  const modalActive = Boolean(pendingApproval || modelPicker || sessionPicker)
  const viewportItems = busy ? withLiveTurnItems(items, reasoningDraft.live, assistantDraft.live) : items
  const baseScrollableLayout = fullscreen || modalActive || scrollOffset > 0
  const baseLayout = layoutRows({
    scrollableLayout: baseScrollableLayout,
    promptOverlay,
    terminalRows,
    promptRows,
    items,
    busy,
    terminalColumns,
    pendingApproval: Boolean(pendingApproval),
    pickerActive: Boolean(modelPicker || sessionPicker)
  })
  const transcriptLines = estimateTranscriptLines(viewportItems, collapsed, toolTimeline.expandedToolIds, terminalColumns)
  const streamingScrollableLayout = busy && transcriptLines > baseLayout.messageRows
  const scrollableLayout = baseScrollableLayout || streamingScrollableLayout
  const mouseTrackingActive = scrollableLayout || busy
  const layout = layoutRows({
    scrollableLayout,
    promptOverlay,
    terminalRows,
    promptRows,
    items,
    busy,
    terminalColumns,
    pendingApproval: Boolean(pendingApproval),
    pickerActive: Boolean(modelPicker || sessionPicker)
  })
  const promptOverlayRows = scrollableLayout && promptOverlay ? promptOverlayRowsForTerminal(terminalRows, promptOverlay) : 0
  const showWelcome = layout.showWelcome
  const overlayRows = layout.overlayRows
  const messageRows = layout.messageRows
  const maxScrollOffset = Math.max(0, transcriptLines - messageRows)
  const canScrollTranscript = scrollableLayout || busy || maxScrollOffset > 0
  const pageScrollRows = Math.max(1, Math.floor(messageRows / 2))
  const wheelScrollRows = Math.max(1, Math.floor(pageScrollRows / 3))
  const pickerRows = Math.max(1, Math.min(6, overlayRows - 6))

  useLayoutEffect(() => {
    if (!isRawModeSupported) return
    setRawMode(true)
    return () => {
      setRawMode(false)
    }
  }, [isRawModeSupported, setRawMode])

  useEffect(() => {
    if (!isRawModeSupported || stdout.isTTY === false) return
    stdout.write(BRACKETED_PASTE_ENABLE)
    stdout.write(CURSOR_STEADY_BAR)
    return () => {
      stdout.write(MOUSE_TRACKING_DISABLE)
      stdout.write(CURSOR_RESET)
      stdout.write(BRACKETED_PASTE_DISABLE)
    }
  }, [isRawModeSupported, stdout])

  useEffect(() => {
    if (!isRawModeSupported || stdout.isTTY === false || !mouseTrackingActive) return
    stdout.write(MOUSE_TRACKING_ENABLE)
    return () => {
      stdout.write(MOUSE_TRACKING_DISABLE)
    }
  }, [isRawModeSupported, mouseTrackingActive, stdout])

  useEffect(() => {
    runtimeRef.current = runtime
  }, [runtime])

  useEffect(() => {
    const previous = previousTranscriptLines.current
    previousTranscriptLines.current = transcriptLines
    if (!scrollableLayout) {
      return
    }
    setScrollOffset(current => {
      return nextScrollOffset({current, previousLines: previous, nextLines: transcriptLines, max: maxScrollOffset})
    })
  }, [scrollableLayout, maxScrollOffset, transcriptLines])

  useEffect(() => {
    const unsubscribe = bridge.onEvent(event => {
      handleBridgeEvent(event)
    })
    bridge.start()
    return () => {
      unsubscribe()
      bridge.stop()
    }
  }, [bridge])

  useSafeInput((input, key) => {
    if (key.ctrl && input === 'o') {
      setCollapsed(current => !current)
      return
    }
    if (key.ctrl && input === 't') {
      toolTimeline.cycleDetails(items)
      return
    }
    if (canScrollTranscript && key.pageUp) {
      scrollTranscript(pageScrollRows)
      return
    }
    if (canScrollTranscript && key.pageDown) {
      scrollTranscript(-pageScrollRows)
      return
    }
    if (canScrollTranscript && key.wheelUp) {
      scrollTranscript(wheelScrollRows)
      return
    }
    if (canScrollTranscript && key.wheelDown) {
      scrollTranscript(-wheelScrollRows)
      return
    }
    if (canScrollTranscript && (key.meta || key.shift) && key.upArrow) {
      scrollTranscript(1)
      return
    }
    if (canScrollTranscript && (key.meta || key.shift) && key.downArrow) {
      scrollTranscript(-1)
      return
    }
  }, {isActive: Boolean(!pendingApproval && !modelPicker && !sessionPicker && isRawModeSupported)})

  function append(item: TranscriptItem) {
    setItems(current => [...current, item])
  }

  function handleBridgeEvent(event: BridgeEvent) {
    if (event.type === 'ready') {
      runtimeRef.current = event.runtime
      setRuntime(event.runtime)
      setWorkspace(event.workspace)
      setProfile(event.profile)
      setPermission(event.permission)
      setSandbox(event.sandbox)
      setToolCount(event.tools.length)
      setCommands(terminalCommands(event.commands))
      setModelProfiles(event.model_profiles ?? [])
      return
    }
    if (event.type === 'turn_started') {
      followLatest()
      setBusy(true)
      activeRunId.current = event.run_id
      turnStartedAt.current = Date.now()
      runtimeEvents.resetLiveState()
      append({kind: 'status', label: 'thinking', text: runtimeLabel(runtimeRef.current?.protocol, runtimeRef.current?.model)})
      return
    }
    if (event.type === 'runtime_event') {
      runtimeEvents.handle(event.event)
      return
    }
    if (event.type === 'turn_finished') {
      runtimeEvents.flushThinking()
      runtimeEvents.flushAssistant()
      setBusy(false)
      activeRunId.current = ''
      if (event.status === 'awaiting_approval') {
        append({kind: 'status', label: 'approval', text: 'waiting for your decision', level: 'warning'})
      } else {
        append({
          kind: 'status',
          label: event.status === 'finished' ? 'done' : event.status === 'error' ? 'stopped' : event.status,
          text: turnStartedAt.current ? `${event.status === 'error' ? 'after ' : ''}${formatDuration(Date.now() - turnStartedAt.current)}` : undefined,
          level: event.status === 'error' ? 'error' : 'info'
        })
        inputQueue.runNext()
      }
      return
    }
    if (event.type === 'model_profiles') {
      setModelProfiles(event.profiles)
      if (suppressNextModelProfiles.current) {
        suppressNextModelProfiles.current = false
        return
      }
      if (modelPickerRequested.current) {
        modelPickerRequested.current = false
        setModelPicker(event.profiles)
      } else {
        append({kind: 'models', profiles: event.profiles})
      }
      return
    }
    if (event.type === 'sessions') {
      if (sessionPickerRequested.current) {
        sessionPickerRequested.current = false
        setSessionPicker(event.sessions)
      } else {
        append({
          kind: 'table',
          title: 'Sessions',
          rows: sessionTableRows(event.sessions)
        })
      }
      return
    }
    if (event.type === 'model_switched') {
      runtimeRef.current = event.runtime
      setRuntime(event.runtime)
      append({kind: 'status', label: 'model', text: `switched to ${event.profile} · ${event.runtime.model}`, level: 'success'})
      return
    }
    if (event.type === 'runtime') {
      runtimeRef.current = event.runtime
      setRuntime(event.runtime)
      append({kind: 'status', label: 'runtime', text: runtimeLabel(event.runtime.protocol, event.runtime.model), level: 'success'})
      return
    }
    if (event.type === 'status') appendTable('Status', event.status)
    else if (event.type === 'doctor') appendTable('Doctor', event.doctor)
    else if (event.type === 'context') appendTable('Context', event.context)
    else if (event.type === 'context_messages') append({kind: 'table', title: 'Context Messages', rows: event.messages})
    else if (event.type === 'trace') append({kind: 'table', title: 'Context Trace', rows: event.trace})
    else if (event.type === 'prompt') append({kind: 'table', title: 'Prompt', rows: event.prompt})
    else if (event.type === 'skills') append({kind: 'table', title: 'Skills', rows: event.skills})
    else if (event.type === 'mcp') append({kind: 'table', title: 'MCP', rows: event.mcp})
    else if (event.type === 'memory') append({kind: 'table', title: 'Memory', rows: event.memory})
    else if (event.type === 'diff') append({kind: 'table', title: 'Diff', rows: event.diff})
    else if (event.type === 'session') append({kind: 'table', title: 'Session', rows: event.session})
    else if (event.type === 'agents') append({kind: 'table', title: 'Agents', rows: event.agents})
    else if (event.type === 'tasks') append({kind: 'table', title: 'Tasks', rows: event.tasks})
    else if (event.type === 'schedules') append({kind: 'table', title: 'Schedules', rows: event.schedules})
    else if (event.type === 'hooks') append({kind: 'table', title: 'Hooks', rows: event.hooks})
    else if (event.type === 'todo') append({kind: 'table', title: 'Todo', rows: event.todo})
    else if (event.type === 'plan') append({kind: 'table', title: 'Plan', rows: event.plan})
    else if (event.type === 'workflows') append({kind: 'table', title: 'Workflows', rows: event.workflows})
    else if (event.type === 'task_queue') append({kind: 'table', title: 'Task Queue', rows: event.queue})
    else if (event.type === 'capabilities') append({kind: 'table', title: 'Capabilities', rows: event.capabilities})
    else if (event.type === 'plugins') append({kind: 'table', title: 'Plugins', rows: event.plugins})
    else if (event.type === 'session_resumed') {
      setItems(transcriptFromSession(event.messages))
      runtimeEvents.resetLiveState()
      setPendingApproval(null)
      setSessionPicker(null)
    }
    else if (event.type === 'workspace') appendTable('Workspace', event.workspace)
    else if (event.type === 'tools') append({kind: 'table', title: 'Tools', rows: toolRows(event.tools)})
    else if (event.type === 'permissions') append({kind: 'table', title: 'Permissions', rows: event.permissions})
    else if (event.type === 'commands') {
      const nextCommands = terminalCommands(event.commands)
      setCommands(nextCommands)
      append({kind: 'table', title: 'Commands', rows: nextCommands.map(command => [command.name, command.description])})
    }
    else if (event.type === 'notice') append({kind: 'status', label: 'notice', text: event.message})
    else if (event.type === 'error') append({kind: 'status', label: 'error', text: event.message, level: 'error'})
    else if (event.type === 'exit') exit()
  }

  function appendTable(title: string, rows: Record<string, unknown>) {
    append({kind: 'table', title, rows: Object.entries(rows).map(([key, value]) => [key, String(value)])})
  }

  function toolRows(tools: ToolDefinition[]): Array<[string, string]> {
    return tools.map(tool => Array.isArray(tool) ? [String(tool[0]), String(tool[1])] : [tool, 'enabled'])
  }

  function scrollTranscript(delta: number) {
    setScrollOffset(current => Math.max(0, Math.min(maxScrollOffset, current + delta)))
  }

  function followLatest() {
    setScrollOffset(0)
  }

  function clearVisibleTranscript() {
    setItems([])
    followLatest()
  }

  function selectModel(name: string) {
    suppressNextModelProfiles.current = true
    setModelPicker(null)
    append({kind: 'status', label: 'model', text: `switching to ${name}`})
    bridge.send({type: 'slash', text: `/model ${name}`})
  }

  function selectSession(id: string) {
    setSessionPicker(null)
    append({kind: 'status', label: 'resume', text: id})
    bridge.send({type: 'slash', text: `/resume ${id}`})
  }

  function decideApproval(decision: ApprovalDecision) {
    if (!pendingApproval) return
    const approved = decision !== 'deny'
    append({
      kind: 'status',
      label: approved ? 'approval' : 'denied',
      text: `${pendingApproval.toolName} · ${decision}`,
      level: approved ? 'success' : 'warning'
    })
    bridge.send({
      type: 'approval',
      run_id: pendingApproval.runId,
      approvals: {[pendingApproval.approvalId]: approved},
      approval_scopes: {[pendingApproval.approvalId]: decision}
    })
    activeRunId.current = pendingApproval.runId
    turnStartedAt.current = Date.now()
    setPendingApproval(null)
    setBusy(true)
  }

  function stop() {
    bridge.stop()
    exit()
  }

  return (
    <Box flexDirection="column" paddingX={1} height={scrollableLayout ? terminalRows : undefined}>
      {showWelcome ? <Welcome runtime={runtime} workspace={workspace} profile={profile} permission={permission} sandbox={sandbox} toolCount={toolCount} /> : null}
      {scrollableLayout ? (
        <MessageViewport items={viewportItems} collapsed={collapsed} selectedToolId={toolTimeline.selectedToolId} expandedToolIds={toolTimeline.expandedToolIds} onToggleTool={toolTimeline.toggle} height={messageRows} scrollOffset={scrollOffset} columns={terminalColumns} />
      ) : (
        <MessageList items={viewportItems} collapsed={collapsed} selectedToolId={toolTimeline.selectedToolId} expandedToolIds={toolTimeline.expandedToolIds} onToggleTool={toolTimeline.toggle} />
      )}
      {scrollableLayout && overlayRows > 0 ? (
        <Box height={overlayRows} flexShrink={0} flexDirection="column">
          {pendingApproval ? <ApprovalPrompt approval={pendingApproval} onDecision={decideApproval} /> : null}
          {modelPicker ? <ModelPicker profiles={modelPicker} onSelect={selectModel} onCancel={() => setModelPicker(null)} maxVisible={pickerRows} /> : null}
          {sessionPicker ? <SessionPicker sessions={sessionPicker} onSelect={selectSession} onCancel={() => setSessionPicker(null)} maxVisible={pickerRows} /> : null}
        </Box>
      ) : (
        <>
          {pendingApproval ? <ApprovalPrompt approval={pendingApproval} onDecision={decideApproval} /> : null}
          {modelPicker ? <ModelPicker profiles={modelPicker} onSelect={selectModel} onCancel={() => setModelPicker(null)} /> : null}
          {sessionPicker ? <SessionPicker sessions={sessionPicker} onSelect={selectSession} onCancel={() => setSessionPicker(null)} /> : null}
        </>
      )}
      {scrollableLayout ? <PromptInputOverlay overlay={promptOverlay} rows={promptOverlayRows} /> : null}
      <PromptInput disabled={Boolean(inputDisabledReason)} disabledReason={inputDisabledReason} repoRoot={repoRoot} commands={commands} modelProfiles={modelProfiles} history={inputHistory} onSubmit={commandRunner.submit} onExit={commandRunner.interruptOrStop} onCancel={commandRunner.interruptActiveRun} onClearScreen={clearVisibleTranscript} onModelPicker={commandRunner.openModelPicker} overlayMode={scrollableLayout} onOverlayChange={setPromptOverlay} onRowsChange={setPromptRows} />
    </Box>
  )
}

export function isFullscreenLayoutEnabled(): boolean {
  return ['1', 'true', 'yes', 'on'].includes(String(process.env.AGENTS_TERMINAL_FULLSCREEN ?? '').toLowerCase())
}

function withLiveTurnItems(items: TranscriptItem[], reasoning: string, assistant: string): TranscriptItem[] {
  if (!reasoning && !assistant) return items
  const liveItems: TranscriptItem[] = []
  if (reasoning) liveItems.push({kind: 'thinking', text: reasoning})
  if (assistant) liveItems.push({kind: 'assistant', text: assistant, live: true})
  return [...items, ...liveItems]
}

function promptOverlayRowsForTerminal(terminalRows: number, overlay: PromptOverlayState): number {
  if (overlay.historySearch?.active) return 1
  if (terminalRows < 20) return 5
  if (terminalRows < 28) return 7
  return PROMPT_OVERLAY_ROWS
}

function layoutRows({
  scrollableLayout,
  promptOverlay,
  terminalRows,
  promptRows,
  items,
  busy,
  terminalColumns,
  pendingApproval,
  pickerActive
}: {
  scrollableLayout: boolean
  promptOverlay: PromptOverlayState | null
  terminalRows: number
  promptRows: number
  items: TranscriptItem[]
  busy: boolean
  terminalColumns: number
  pendingApproval: boolean
  pickerActive: boolean
}): {showWelcome: boolean; overlayRows: number; messageRows: number} {
  const promptOverlayRows = scrollableLayout && promptOverlay ? promptOverlayRowsForTerminal(terminalRows, promptOverlay) : 0
  const showWelcome = items.length === 0 && !busy && terminalColumns >= 80 && (!scrollableLayout || terminalRows >= promptRows + WELCOME_ROWS + 4)
  const overlayRows = pendingApproval
    ? Math.min(APPROVAL_ROWS, Math.max(6, terminalRows - promptRows - promptOverlayRows - 1))
    : pickerActive
      ? Math.min(PICKER_ROWS, Math.max(6, terminalRows - promptRows - promptOverlayRows - 1))
      : 0
  const chromeRows = promptRows + promptOverlayRows + overlayRows + (showWelcome ? WELCOME_ROWS : 0)
  return {showWelcome, overlayRows, messageRows: Math.max(1, terminalRows - chromeRows)}
}
