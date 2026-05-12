import React, {type ReactNode} from 'react'
import {Box, Text, useStdout} from 'ink'
import {colors} from '../../ui/theme.js'
import {Divider} from './Divider.js'

export function Dialog({
  title,
  subtitle,
  children,
  footer,
  borderColor = colors.border,
  width = 88
}: {
  title: string
  subtitle?: string
  children: ReactNode
  footer?: ReactNode
  borderColor?: string
  width?: number
}) {
  const {stdout} = useStdout()
  const columns = typeof stdout.columns === 'number' ? stdout.columns : width
  const dialogWidth = Math.min(width, Math.max(24, columns - 2))
  return (
    <Box flexDirection="column" marginTop={1} borderStyle="round" borderColor={borderColor} paddingX={1} width={dialogWidth}>
      <Box>
        <Text color={borderColor} bold>{title}</Text>
        {subtitle ? <Text dimColor>  {subtitle}</Text> : null}
      </Box>
      <Box flexDirection="column" marginTop={1}>
        {children}
      </Box>
      {footer ? (
        <Box flexDirection="column" marginTop={1}>
          <Divider width={Math.max(20, dialogWidth - 4)} color={colors.dim} />
          {footer}
        </Box>
      ) : null}
    </Box>
  )
}
