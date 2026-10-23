import {useRef, useState} from 'react'
import type {ModelProfile, PendingApproval, RuntimeInfo, SessionRecord, WorkspaceInfo} from '../protocol/terminalHostProtocol.js'
import type {TranscriptItem} from '../components/MessageList.js'
import type {PromptOverlayState} from '../components/PromptInput.js'
import {usePersistentHistory} from '../hooks/usePersistentHistory.js'
import {terminalCommands, type CommandDef} from '../ui/commands.js'
import {PROMPT_BASE_ROWS} from './terminalLayout.js'

export function useTerminalAppState(repoRoot: string) {
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
  const hasInterruptibleToolInProgress = useRef(false)
  const turnStartedAt = useRef(0)
  const previousTranscriptLines = useRef(0)
  const modelPickerRequested = useRef(false)
  const sessionPickerRequested = useRef(false)
  const suppressNextModelProfiles = useRef(false)

  return {
    runtime,
    setRuntime,
    workspace,
    setWorkspace,
    profile,
    setProfile,
    permission,
    setPermission,
    sandbox,
    setSandbox,
    toolCount,
    setToolCount,
    items,
    setItems,
    busy,
    setBusy,
    collapsed,
    setCollapsed,
    scrollOffset,
    setScrollOffset,
    inputHistory,
    addInputHistory,
    modelProfiles,
    setModelProfiles,
    commands,
    setCommands,
    modelPicker,
    setModelPicker,
    sessionPicker,
    setSessionPicker,
    promptOverlay,
    setPromptOverlay,
    promptRows,
    setPromptRows,
    pendingApproval,
    setPendingApproval,
    runtimeRef,
    activeRunId,
    hasInterruptibleToolInProgress,
    turnStartedAt,
    previousTranscriptLines,
    modelPickerRequested,
    sessionPickerRequested,
    suppressNextModelProfiles
  }
}
