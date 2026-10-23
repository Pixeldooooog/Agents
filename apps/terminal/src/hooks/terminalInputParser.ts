import parseKeypress, {nonAlphanumericKeys} from '../../node_modules/ink/build/parse-keypress.js'

export type Key = {
  upArrow: boolean
  downArrow: boolean
  leftArrow: boolean
  rightArrow: boolean
  pageDown: boolean
  pageUp: boolean
  home: boolean
  end: boolean
  return: boolean
  escape: boolean
  ctrl: boolean
  shift: boolean
  tab: boolean
  backspace: boolean
  delete: boolean
  mouse: boolean
  wheelUp: boolean
  wheelDown: boolean
  meta: boolean
  super?: boolean
  hyper?: boolean
  capsLock?: boolean
  numLock?: boolean
  eventType?: string
}

export function parseTerminalInput(rawInput: string): {input: string; key: Key} {
  const keypress = parseKeypress(rawInput)
  const mouse = parseMouseEvent(rawInput)
  const navigation = parseNavigationEvent(rawInput)
  const key: Key = {
    upArrow: navigation.upArrow || keypress.name === 'up',
    downArrow: navigation.downArrow || keypress.name === 'down',
    leftArrow: navigation.leftArrow || keypress.name === 'left',
    rightArrow: navigation.rightArrow || keypress.name === 'right',
    pageDown: navigation.pageDown || keypress.name === 'pagedown',
    pageUp: navigation.pageUp || keypress.name === 'pageup',
    home: navigation.home || keypress.name === 'home',
    end: navigation.end || keypress.name === 'end',
    return: keypress.name === 'return',
    escape: keypress.name === 'escape',
    ctrl: Boolean(keypress.ctrl),
    shift: Boolean(keypress.shift),
    tab: keypress.name === 'tab',
    backspace: keypress.name === 'backspace',
    delete: navigation.delete || keypress.name === 'delete',
    mouse: Boolean(mouse),
    wheelUp: mouse?.wheel === 'up',
    wheelDown: mouse?.wheel === 'down',
    meta: Boolean(keypress.meta || keypress.name === 'escape' || keypress.option),
    super: keypress.super ?? false,
    hyper: keypress.hyper ?? false,
    capsLock: keypress.capsLock ?? false,
    numLock: keypress.numLock ?? false,
    eventType: keypress.eventType
  }
  return {
    input: mouse ? '' : inputFromKeypress(rawInput, keypress, key),
    key
  }
}

export function splitTerminalControlEvents(input: string): string[] {
  const events: string[] = []
  let index = 0
  while (index < input.length) {
    const event = readTerminalControlEvent(input.slice(index))
    if (!event) return [input]
    events.push(event)
    index += event.length
  }
  return events.length ? events : [input]
}

export function parseMouseEvent(input: string): {wheel?: 'up' | 'down'} | undefined {
  const sgr = /^\u001B\[<(\d+);\d+;\d+[Mm]$/.exec(input)
  if (sgr) {
    const button = Number(sgr[1])
    if ((button & 0x40) !== 0 && button < 128) return {wheel: (button & 1) === 0 ? 'up' : 'down'}
    return {}
  }
  if (input.length === 6 && input.startsWith('\u001B[M')) {
    const button = input.charCodeAt(3) - 32
    if ((button & 0x40) === 0) return {}
    return {wheel: (button & 1) === 0 ? 'up' : 'down'}
  }
  return undefined
}

export function parseNavigationEvent(input: string): Partial<Key> {
  const tilde = /^\u001B\[(\d+)(?:;[\d:]+)?~$/.exec(input)
  if (tilde) {
    if (tilde[1] === '5') return {pageUp: true}
    if (tilde[1] === '6') return {pageDown: true}
    if (tilde[1] === '1' || tilde[1] === '7') return {home: true}
    if (tilde[1] === '4' || tilde[1] === '8') return {end: true}
    if (tilde[1] === '3') return {delete: true}
  }
  const csi = /^\u001B\[(?:1;[\d:]+)?([ABCDHF])$/.exec(input)
  const app = /^\u001BO([ABCDHF])$/.exec(input)
  const code = csi?.[1] ?? app?.[1]
  if (code === 'A') return {upArrow: true}
  if (code === 'B') return {downArrow: true}
  if (code === 'C') return {rightArrow: true}
  if (code === 'D') return {leftArrow: true}
  if (code === 'H') return {home: true}
  if (code === 'F') return {end: true}
  return {}
}

function readTerminalControlEvent(input: string): string | undefined {
  const sgrMouse = /^\u001B\[<\d+;\d+;\d+[Mm]/.exec(input)
  if (sgrMouse) return sgrMouse[0]
  if (input.length >= 6 && input.startsWith('\u001B[M')) return input.slice(0, 6)
  const tilde = /^\u001B\[\d+(?:;[\d:]+)?~/.exec(input)
  if (tilde) return tilde[0]
  const csi = /^\u001B\[(?:1;[\d:]+)?[ABCDHF]/.exec(input)
  if (csi) return csi[0]
  const app = /^\u001BO[ABCDHF]/.exec(input)
  if (app) return app[0]
  return undefined
}

function inputFromKeypress(data: unknown, keypress: ReturnType<typeof parseKeypress>, key: Key): string {
  let input = ''
  const name = typeof keypress.name === 'string' ? keypress.name : ''
  if (keypress.isKittyProtocol) {
    if (keypress.isPrintable) input = keypress.text ?? name
    else if (keypress.ctrl && name.length === 1) input = name
  } else if (keypress.ctrl) {
    input = name
  } else {
    input = keypress.sequence ?? String(data ?? '')
  }
  if (typeof input !== 'string') input = String(data ?? '')
  if (!keypress.isKittyProtocol && nonAlphanumericKeys.includes(name)) input = ''
  if (input.startsWith('\u001B')) input = input.slice(1)
  if (input.length === 1 && /[A-Z]/.test(input[0] ?? '')) key.shift = true
  return input
}
