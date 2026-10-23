import React from 'react'
import {Box} from 'ink'
import {ApprovalPrompt} from '../components/ApprovalPrompt.js'
import {ModelPicker} from '../components/ModelPicker.js'
import {SessionPicker} from '../components/SessionPicker.js'
import type {ApprovalDecision, ModelProfile, PendingApproval, SessionRecord} from '../protocol/terminalHostProtocol.js'

export function TerminalOverlays({
  scrollableLayout,
  overlayRows,
  pendingApproval,
  modelPicker,
  sessionPicker,
  pickerRows,
  onApprovalDecision,
  onSelectModel,
  onCancelModel,
  onSelectSession,
  onCancelSession
}: {
  scrollableLayout: boolean
  overlayRows: number
  pendingApproval: PendingApproval | null
  modelPicker: ModelProfile[] | null
  sessionPicker: SessionRecord[] | null
  pickerRows: number
  onApprovalDecision: (decision: ApprovalDecision) => void
  onSelectModel: (name: string) => void
  onCancelModel: () => void
  onSelectSession: (id: string) => void
  onCancelSession: () => void
}) {
  const content = (
    <>
      {pendingApproval ? <ApprovalPrompt approval={pendingApproval} onDecision={onApprovalDecision} /> : null}
      {modelPicker ? <ModelPicker profiles={modelPicker} onSelect={onSelectModel} onCancel={onCancelModel} maxVisible={scrollableLayout ? pickerRows : undefined} /> : null}
      {sessionPicker ? <SessionPicker sessions={sessionPicker} onSelect={onSelectSession} onCancel={onCancelSession} maxVisible={scrollableLayout ? pickerRows : undefined} /> : null}
    </>
  )

  if (scrollableLayout && overlayRows > 0) {
    return (
      <Box height={overlayRows} flexShrink={0} flexDirection="column">
        {content}
      </Box>
    )
  }

  return content
}
