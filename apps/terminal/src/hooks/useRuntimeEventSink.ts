import {useRef, type Dispatch, type MutableRefObject, type SetStateAction} from 'react'
import type {PendingApproval, RuntimeEvent} from '../protocol/types.js'
import type {TranscriptItem} from '../components/MessageList.js'
import {approvalDecisionText, pendingApprovalFromEvent, retryText, runtimeErrorStatus} from '../ui/runtimeEvents.js'
import {useLiveDraft} from './useLiveDraft.js'
import {useToolTimeline} from './useToolTimeline.js'

export function useRuntimeEventSink({
  activeRunId,
  hasInterruptibleToolInProgress,
  append,
  setItems,
  setPendingApproval
}: {
  activeRunId: MutableRefObject<string>
  hasInterruptibleToolInProgress: MutableRefObject<boolean>
  append: (item: TranscriptItem) => void
  setItems: Dispatch<SetStateAction<TranscriptItem[]>>
  setPendingApproval: Dispatch<SetStateAction<PendingApproval | null>>
}) {
  const assistantDraft = useLiveDraft()
  const reasoningDraft = useLiveDraft({trimLive: true})
  const toolTimeline = useToolTimeline(setItems)
  const assistantCompleted = useRef(false)
  const activeToolInterrupts = useRef(new Map<string, 'cancel' | 'block'>())

  function handle(event: RuntimeEvent) {
    const payload = event.payload ?? {}
    if (event.type === 'text_delta') {
      assistantCompleted.current = false
      assistantDraft.append(String(payload.delta ?? ''))
      return
    }
    if (event.type === 'model_message') {
      flushThinking()
      const finalText = String(payload.content ?? '') || assistantDraft.value()
      assistantDraft.clear()
      if (finalText) {
        append({kind: 'assistant', text: finalText})
        assistantCompleted.current = true
      }
      return
    }
    if (event.type === 'reasoning_delta') {
      reasoningDraft.append(String(payload.delta ?? ''))
      return
    }
    if (event.type === 'model_retry') {
      append({kind: 'status', label: 'retry', text: retryText(payload), level: 'warning'})
      return
    }
    if (event.type === 'tool_start') {
      flushThinking()
      flushAssistant()
      trackToolStart(payload)
      toolTimeline.start(event, payload)
      return
    }
    if (event.type === 'tool_result') {
      trackToolFinish(payload)
      toolTimeline.finish(event, payload)
      return
    }
    if (event.type === 'tool_approval_required') {
      flushThinking()
      flushAssistant()
      setPendingApproval(pendingApprovalFromEvent(event, activeRunId.current))
      return
    }
    if (event.type === 'tool_approval_decision') {
      const decision = approvalDecisionText(event)
      append({
        kind: 'status',
        label: decision.approved ? 'approved' : 'denied',
        text: decision.text,
        level: decision.approved ? 'success' : 'warning'
      })
      return
    }
    if (event.type === 'error') {
      flushThinking()
      flushAssistant()
      append({kind: 'status', ...runtimeErrorStatus(String(payload.message ?? 'runtime error'))})
      return
    }
    if (event.type === 'done') {
      const text = String(payload.content ?? '')
      if (payload.status === 'finished' && text && !assistantDraft.value() && !assistantCompleted.current) {
        append({kind: 'assistant', text})
        assistantCompleted.current = true
      }
    }
  }

  function flushAssistant() {
    const text = assistantDraft.flush()
    if (!text) return
    append({kind: 'assistant', text})
    assistantCompleted.current = true
  }

  function flushThinking() {
    const text = reasoningDraft.flush({trim: true})
    if (!text) return
    append({kind: 'thinking', text})
  }

  function resetLiveState() {
    assistantDraft.clear()
    reasoningDraft.clear()
    assistantCompleted.current = false
    toolTimeline.reset()
    activeToolInterrupts.current.clear()
    hasInterruptibleToolInProgress.current = false
  }

  function trackToolStart(payload: Record<string, unknown>) {
    const id = String(payload.id ?? payload.tool_call_id ?? '')
    if (!id) return
    activeToolInterrupts.current.set(id, interruptBehaviorFromPayload(payload))
    updateInterruptibleState()
  }

  function trackToolFinish(payload: Record<string, unknown>) {
    const id = String(payload.tool_call_id ?? payload.id ?? '')
    if (!id) return
    activeToolInterrupts.current.delete(id)
    updateInterruptibleState()
  }

  function updateInterruptibleState() {
    const behaviors = [...activeToolInterrupts.current.values()]
    hasInterruptibleToolInProgress.current = behaviors.length > 0 && behaviors.every(value => value === 'cancel')
  }

  return {assistantDraft, reasoningDraft, toolTimeline, handle, flushAssistant, flushThinking, resetLiveState}
}

function interruptBehaviorFromPayload(payload: Record<string, unknown>): 'cancel' | 'block' {
  const contract = payload.contract
  if (!contract || typeof contract !== 'object') return 'block'
  const metadata = (contract as {metadata?: unknown}).metadata
  if (!metadata || typeof metadata !== 'object') return 'block'
  return (metadata as {interrupt_behavior?: unknown}).interrupt_behavior === 'cancel' ? 'cancel' : 'block'
}
