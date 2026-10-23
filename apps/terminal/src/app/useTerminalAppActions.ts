import type {TranscriptItem} from '../components/MessageList.js'
import type {TerminalHostClient} from '../protocol/terminalHostClient.js'
import type {ApprovalDecision} from '../protocol/terminalHostProtocol.js'
import type {useTerminalAppState} from './useTerminalAppState.js'

type TerminalAppActionsOptions = {
  appState: ReturnType<typeof useTerminalAppState>
  terminalHost: TerminalHostClient
  exit: () => void
}

export function useTerminalAppActions({appState, terminalHost, exit}: TerminalAppActionsOptions) {
  function append(item: TranscriptItem) {
    appState.setItems(current => [...current, item])
  }

  function followLatest() {
    appState.setScrollOffset(0)
  }

  function scrollTranscript(delta: number, maxScrollOffset: number) {
    appState.setScrollOffset(current => Math.max(0, Math.min(maxScrollOffset, current + delta)))
  }

  function clearVisibleTranscript() {
    appState.setItems([])
    followLatest()
  }

  function selectModel(name: string) {
    appState.suppressNextModelProfiles.current = true
    appState.setModelPicker(null)
    append({kind: 'status', label: 'model', text: `switching to ${name}`})
    terminalHost.send({type: 'slash', text: `/model ${name}`})
  }

  function selectSession(id: string) {
    appState.setSessionPicker(null)
    append({kind: 'status', label: 'resume', text: id})
    terminalHost.send({type: 'slash', text: `/resume ${id}`})
  }

  function decideApproval(decision: ApprovalDecision) {
    const pendingApproval = appState.pendingApproval
    if (!pendingApproval) return
    const approved = decision !== 'deny'
    append({
      kind: 'status',
      label: approved ? 'approval' : 'denied',
      text: `${pendingApproval.toolName} · ${decision}`,
      level: approved ? 'success' : 'warning'
    })
    terminalHost.send({
      type: 'approval',
      run_id: pendingApproval.runId,
      approvals: {[pendingApproval.approvalId]: approved},
      approval_scopes: {[pendingApproval.approvalId]: decision}
    })
    appState.activeRunId.current = pendingApproval.runId
    appState.turnStartedAt.current = Date.now()
    appState.setPendingApproval(null)
    appState.setBusy(true)
  }

  function stop() {
    terminalHost.stop()
    exit()
  }

  return {
    append,
    followLatest,
    scrollTranscript,
    clearVisibleTranscript,
    selectModel,
    selectSession,
    decideApproval,
    stop
  }
}
