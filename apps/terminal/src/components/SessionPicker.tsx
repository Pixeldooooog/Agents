import React, {useMemo} from 'react'
import {Text} from 'ink'
import type {SessionRecord} from '../protocol/types.js'
import {colors} from '../ui/theme.js'
import {Dialog} from './design/Dialog.js'
import {Select, type SelectOption} from './design/Select.js'
import {ShortcutHint} from './design/ShortcutHint.js'

export function SessionPicker({
  sessions,
  onSelect,
  onCancel,
  maxVisible = 6
}: {
  sessions: SessionRecord[]
  onSelect: (id: string) => void
  onCancel: () => void
  maxVisible?: number
}) {
  const options: Array<SelectOption<string>> = useMemo(() => sessions.map(session => ({
    value: session.id,
    label: session.short_id.padEnd(24),
    meta: `${session.messages} messages · ${session.model}`,
    description: `${session.updated}${session.workspace ? ` · ${session.workspace}` : ''}`
  })), [sessions])

  return (
    <Dialog
      title="Resume Session"
      subtitle={sessions[0] ? `${sessions.length} saved` : undefined}
      borderColor={colors.border}
      footer={<ShortcutHint items={[['↑/↓', 'move'], ['enter', 'resume'], ['esc', 'cancel']]} />}
    >
      <Select options={options} onSelect={onSelect} onCancel={onCancel} filterable emptyLabel="No saved sessions" maxVisible={maxVisible} />
    </Dialog>
  )
}
