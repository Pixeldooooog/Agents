import {useEffect, useLayoutEffect} from 'react'
import {
  BRACKETED_PASTE_DISABLE,
  BRACKETED_PASTE_ENABLE,
  CURSOR_RESET,
  CURSOR_STEADY_BAR,
  MOUSE_TRACKING_DISABLE,
  MOUSE_TRACKING_ENABLE
} from './terminalLayout.js'

type TerminalOutput = {
  isTTY?: boolean
  write: (text: string) => void
}

type TerminalModeOptions = {
  isRawModeSupported: boolean
  mouseTrackingActive: boolean
  setRawMode: (enabled: boolean) => void
  stdout: TerminalOutput
}

export function useTerminalModeEffects(options: TerminalModeOptions) {
  useLayoutEffect(() => {
    if (!options.isRawModeSupported) return
    options.setRawMode(true)
    return () => {
      options.setRawMode(false)
    }
  }, [options.isRawModeSupported, options.setRawMode])

  useEffect(() => {
    if (!options.isRawModeSupported || options.stdout.isTTY === false) return
    options.stdout.write(BRACKETED_PASTE_ENABLE)
    options.stdout.write(CURSOR_STEADY_BAR)
    return () => {
      options.stdout.write(MOUSE_TRACKING_DISABLE)
      options.stdout.write(CURSOR_RESET)
      options.stdout.write(BRACKETED_PASTE_DISABLE)
    }
  }, [options.isRawModeSupported, options.stdout])

  useEffect(() => {
    if (!options.isRawModeSupported || options.stdout.isTTY === false || !options.mouseTrackingActive) return
    options.stdout.write(MOUSE_TRACKING_ENABLE)
    return () => {
      options.stdout.write(MOUSE_TRACKING_DISABLE)
    }
  }, [options.isRawModeSupported, options.mouseTrackingActive, options.stdout])
}
