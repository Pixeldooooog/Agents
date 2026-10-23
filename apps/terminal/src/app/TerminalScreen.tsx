import React from 'react'
import {Box} from 'ink'
import {Welcome} from '../components/Welcome.js'
import type {TranscriptItem} from '../components/MessageList.js'
import {PromptInput, PromptInputOverlay, type PromptOverlayState} from '../components/PromptInput.js'
import type {ApprovalDecision, ModelProfile, PendingApproval, RuntimeInfo, SessionRecord, WorkspaceInfo} from '../protocol/terminalHostProtocol.js'
import type {CommandDef} from '../ui/commands.js'
import {TerminalOverlays} from './TerminalOverlays.js'
import {TerminalTranscript} from './TerminalTranscript.js'
import type {TerminalViewState} from './terminalViewState.js'

export type TerminalScreenProps = {
  repoRoot: string
  viewState: TerminalViewState
  promptOverlay: PromptOverlayState | null
  terminalRows: number
  welcome: TerminalWelcomeProps
  transcript: TerminalTranscriptProps
  overlays: TerminalOverlayProps
  prompt: TerminalPromptProps
  onOverlayChange: (overlay: PromptOverlayState | null) => void
  onRowsChange: (rows: number) => void
}

type TerminalWelcomeProps = {
  runtime?: RuntimeInfo
  workspace?: WorkspaceInfo
  profile: string
  permission: string
  sandbox: string
  toolCount: number
}

type TerminalTranscriptProps = {
  collapsed: boolean
  selectedToolId?: string
  expandedToolIds: Set<string>
  scrollOffset: number
  terminalColumns: number
  onToggleTool: (toolCallId: string) => void
}

type TerminalOverlayProps = {
  pendingApproval: PendingApproval | null
  modelPicker: ModelProfile[] | null
  sessionPicker: SessionRecord[] | null
  onApprovalDecision: (decision: ApprovalDecision) => void
  onSelectModel: (name: string) => void
  onCancelModel: () => void
  onSelectSession: (id: string) => void
  onCancelSession: () => void
}

type TerminalPromptProps = {
  commands: CommandDef[]
  modelProfiles: ModelProfile[]
  inputHistory: string[]
  inputDisabledReason?: string
  onSubmit: (value: string, displayValue?: string) => void
  onExit: () => void | boolean
  onCancel: () => void | boolean
  onClearScreen: () => void
  onModelPicker: () => void
}

export function TerminalScreen({
  repoRoot,
  viewState,
  promptOverlay,
  terminalRows,
  welcome,
  transcript,
  overlays,
  prompt,
  onOverlayChange,
  onRowsChange
}: TerminalScreenProps) {
  const {
    viewportItems,
    scrollableLayout,
    showWelcome,
    overlayRows,
    messageRows,
    pickerRows,
    promptOverlayRows
  } = viewState
  return (
    <Box flexDirection="column" paddingX={1} height={scrollableLayout ? terminalRows : undefined}>
      {showWelcome ? <Welcome runtime={welcome.runtime} workspace={welcome.workspace} profile={welcome.profile} permission={welcome.permission} sandbox={welcome.sandbox} toolCount={welcome.toolCount} /> : null}
      <TerminalTranscript scrollableLayout={scrollableLayout} items={viewportItems} collapsed={transcript.collapsed} selectedToolId={transcript.selectedToolId} expandedToolIds={transcript.expandedToolIds} onToggleTool={transcript.onToggleTool} messageRows={messageRows} scrollOffset={transcript.scrollOffset} terminalColumns={transcript.terminalColumns} />
      <TerminalOverlays scrollableLayout={scrollableLayout} overlayRows={overlayRows} pendingApproval={overlays.pendingApproval} modelPicker={overlays.modelPicker} sessionPicker={overlays.sessionPicker} pickerRows={pickerRows} onApprovalDecision={overlays.onApprovalDecision} onSelectModel={overlays.onSelectModel} onCancelModel={overlays.onCancelModel} onSelectSession={overlays.onSelectSession} onCancelSession={overlays.onCancelSession} />
      {scrollableLayout ? <PromptInputOverlay overlay={promptOverlay} rows={promptOverlayRows} /> : null}
      <PromptInput disabled={Boolean(prompt.inputDisabledReason)} disabledReason={prompt.inputDisabledReason} repoRoot={repoRoot} commands={prompt.commands} modelProfiles={prompt.modelProfiles} history={prompt.inputHistory} onSubmit={prompt.onSubmit} onExit={prompt.onExit} onCancel={prompt.onCancel} onClearScreen={prompt.onClearScreen} onModelPicker={prompt.onModelPicker} overlayMode={scrollableLayout} onOverlayChange={onOverlayChange} onRowsChange={onRowsChange} />
    </Box>
  )
}
