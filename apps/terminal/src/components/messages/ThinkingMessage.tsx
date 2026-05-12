import React from 'react'
import {Box, Text} from 'ink'
import {colors} from '../../ui/theme.js'
import {MarkdownBlock} from '../MarkdownBlock.js'
import {MessageResponse} from '../MessageResponse.js'

import {LiveBadge} from '../design/LiveBadge.js'

export function ThinkingMessage({text, collapsed, live}: {text: string; collapsed: boolean; live?: boolean}) {
  if (collapsed) {
    return (
      <Box marginTop={1}>
        <Text color={colors.dim} italic>∴ Thinking</Text>
        {live ? <LiveBadge /> : null}
        <Text color={colors.dim}>  ctrl+o to expand</Text>
      </Box>
    )
  }

  return (
    <Box marginTop={1} flexDirection="column">
      <Text color={colors.dim} italic>∴ Thinking expanded{live ? <LiveBadge /> : null}</Text>
      <MessageResponse>
        <MarkdownBlock text={text} collapsed={false} maxLines={5} dim />
      </MessageResponse>
    </Box>
  )
}
