import React from 'react'
import {Box} from 'ink'
import {AssistantMessage} from './messages/AssistantMessage.js'
import {ThinkingMessage} from './messages/ThinkingMessage.js'
import {ThinkingLine} from './ThinkingLine.js'

export function LiveTurn({
  assistant,
  reasoning,
  label,
  collapsed,
  maxLines
}: {
  assistant: string
  reasoning: string
  label: string
  collapsed: boolean
  maxLines?: number
}) {
  if (assistant || reasoning) {
    const liveCollapsed = typeof maxLines === 'number'
    const assistantLines = typeof maxLines === 'number' ? Math.max(1, maxLines - (reasoning ? 1 : 0)) : undefined
    return (
      <Box flexDirection="column">
        {reasoning ? <ThinkingMessage text={reasoning} collapsed={collapsed} live /> : null}
        {assistant ? <AssistantMessage text={assistant} collapsed={liveCollapsed} maxLines={assistantLines} live /> : null}
      </Box>
    )
  }
  return <ThinkingLine label={label} />
}
