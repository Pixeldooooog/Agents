import React from 'react'
import {Box, Text} from 'ink'
import {colors} from '../../ui/theme.js'
import {MarkdownBlock} from '../MarkdownBlock.js'
import {MessageResponse} from '../MessageResponse.js'

import {LiveBadge} from '../design/LiveBadge.js'

export function AssistantMessage({
  text,
  collapsed,
  live,
  maxLines
}: {
  text: string
  collapsed: boolean
  live?: boolean
  maxLines?: number
}) {
  return (
    <Box marginTop={1} flexDirection="column">
      <Box>
        <Text color={colors.success}>● </Text>
        <Text color={colors.text} bold>Assistant Reply</Text>
        {live ? <LiveBadge /> : null}
      </Box>
      <MessageResponse>
        <MarkdownBlock text={text} collapsed={collapsed} maxLines={maxLines} />
      </MessageResponse>
    </Box>
  )
}
