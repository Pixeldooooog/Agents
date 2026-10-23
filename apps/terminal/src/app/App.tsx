import React from 'react'
import {TerminalScreen} from './TerminalScreen.js'
import {type TerminalAppProps, useTerminalAppController} from './useTerminalAppController.js'

export function App(props: TerminalAppProps) {
  const screenProps = useTerminalAppController(props)
  return <TerminalScreen {...screenProps} />
}
