import assert from 'node:assert/strict'
import {tmpdir} from 'node:os'
import path from 'node:path'
import {Readable, Writable} from 'node:stream'
import React from 'react'
import {render, type Instance, type RenderOptions} from 'ink'
import {App, isFullscreenLayoutEnabled} from '../src/App.js'

const repoRoot = path.resolve(process.cwd(), '../..')
const srcPath = path.join(repoRoot, 'src')
const fixturePath = path.join(repoRoot, 'apps/terminal/scripts/fixtures')
process.env.PYTHONPATH = [srcPath, fixturePath, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter)
process.env.AGENTS_TERMINAL_HISTORY_PATH = path.join(tmpdir(), `agents-terminal-flow-history-${process.pid}.json`)
process.env.AGENTS_TERMINAL_SESSION_STORE = path.join(tmpdir(), `agents-terminal-flow-sessions-${process.pid}`)
const fullscreenLayout = isFullscreenLayoutEnabled()

async function waitForOutput(output: TestOutput, expected: string, timeoutMs = 5000): Promise<void> {
  const startedAt = Date.now()
  while (!output.content.includes(expected)) {
    if (Date.now() - startedAt > timeoutMs) {
      throw new Error(`timed out waiting for ${expected}; output was:\n${output.content.slice(-2500)}`)
    }
    await settle(40)
  }
}

async function waitForOutputAfter(output: TestOutput, expected: string, marker: number, timeoutMs = 5000): Promise<void> {
  const startedAt = Date.now()
  while (!output.content.slice(marker).includes(expected)) {
    if (Date.now() - startedAt > timeoutMs) {
      throw new Error(`timed out waiting for ${expected} after marker; output was:\n${output.content.slice(marker).slice(-2500)}`)
    }
    await settle(40)
  }
}

async function waitUntilExit(instance: Instance, output: TestOutput, timeoutMs = 5000): Promise<void> {
  const wait = (instance as unknown as {waitUntilExit?: () => Promise<void>}).waitUntilExit
  if (!wait) {
    await settle(250)
    return
  }
  await Promise.race([
    wait.call(instance),
    new Promise((_resolve, reject) => setTimeout(() => reject(new Error(`timed out waiting for app exit; output was:\n${output.content.slice(-2500)}`)), timeoutMs))
  ])
}

function settle(ms = 40): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}

async function clearPromptInput(): Promise<void> {
  stdin.press('\u0015')
  await settle()
}

class TestInput extends Readable {
  isTTY = true
  isRaw = false

  _read() {}

  setRawMode(value: boolean): this {
    this.isRaw = value
    return this
  }

  ref(): this {
    return this
  }

  unref(): this {
    return this
  }

  press(value: string): void {
    this.push(Buffer.from(value))
    this.emit('readable')
  }
}

class TestOutput extends Writable {
  columns = 100
  rows = 30
  isTTY = true
  content = ''

  _write(chunk: unknown, _encoding: BufferEncoding, callback: (error?: Error | null) => void): void {
    this.content += String(chunk)
    callback()
  }

  clearLine(_dir?: number, callback?: () => void): boolean {
    callback?.()
    return true
  }

  clearScreenDown(callback?: () => void): boolean {
    callback?.()
    return true
  }

  cursorTo(_x: number, _y?: number | (() => void), callback?: () => void): boolean {
    if (typeof _y === 'function') _y()
    else callback?.()
    return true
  }

  moveCursor(_dx: number, _dy: number, callback?: () => void): boolean {
    callback?.()
    return true
  }

  getColorDepth(): number {
    return 8
  }

  resize(columns: number, rows: number): void {
    this.columns = columns
    this.rows = rows
    this.emit('resize')
  }
}

const stdin = new TestInput()
const stdout = new TestOutput()
const stderr = new TestOutput()
const consoleMessages: string[] = []
const originalWarn = console.warn
const originalError = console.error
let instance: Instance | undefined

try {
  console.warn = (...args: unknown[]) => consoleMessages.push(args.map(String).join(' '))
  console.error = (...args: unknown[]) => consoleMessages.push(args.map(String).join(' '))
  instance = render(
    <App python=".venv/bin/python" repoRoot={repoRoot} bridgeArgs={[]} bridgeModule="terminal_bridge_fixture" />,
    {
      stdin,
      stdout,
      stderr,
      exitOnCtrlC: false,
      patchConsole: false
    } as unknown as RenderOptions
  )

  await waitForOutput(stdout, 'Agents Code')
  stdin.press('/diff')
  await settle()
  stdin.press('\r')
  await waitForOutput(stdout, 'Diff')
  await waitForOutput(stdout, 'fixture.txt')

  stdin.press('hello fixture')
  await settle()
  stdin.press('\r')
  await waitForOutput(stdout, 'fixture answer: hello fixture')

  const beforeLargePaste = stdout.content.length
  const largeSlashPaste = [
    '/large-paste-message',
    ...Array.from({length: 420}, (_, index) => `paste-line-${index + 1}-${'x'.repeat(32)}`)
  ].join('\n')
  stdin.press(largeSlashPaste)
  await waitForOutputAfter(stdout, '[...Pasted text #1 +421 lines...]', beforeLargePaste)
  assert.equal(stdout.content.slice(beforeLargePaste).includes('paste-line-300'), false, 'large paste should be represented by a compact prompt reference')
  stdin.press('\r')
  await waitForOutputAfter(stdout, 'large paste received', beforeLargePaste)
  assert.equal(stdout.content.slice(beforeLargePaste).includes('large paste was treated as a slash command'), false)

  const beforeToolTurn = stdout.content.length
  stdin.press('tool turn')
  await settle()
  stdin.press('\r')
  await waitForOutput(stdout, 'Read file: fixture.txt')
  await waitForOutput(stdout, 'filesystem.read')
  const collapsedToolOutput = stdout.content.slice(beforeToolTurn)
  assert.equal(collapsedToolOutput.includes('Details'), false)
  assert.equal(collapsedToolOutput.includes('fixture file body'), false)
  stdin.press('\u0014')
  await waitForOutput(stdout, 'Input')
  await waitForOutput(stdout, 'fixture file body')

  stdin.press('retry turn')
  await settle()
  stdin.press('\r')
  await waitForOutput(stdout, 'fixture transient failure')
  await waitForOutput(stdout, 'fixture retry recovered')

  const beforeLongOutput = stdout.content.length
  stdin.press('long output')
  await settle()
  stdin.press('\r')
  await waitForOutput(stdout, 'long-line-20')
  const longOutput = stdout.content.slice(beforeLongOutput)
  assert.equal(longOutput.includes('blocks hidden'), false)
  assert.equal(longOutput.includes('----------------'), true, 'finished assistant replies should render a divider after the final answer')
  if (!fullscreenLayout) {
    assert.equal(longOutput.includes('long-line-01'), true, 'default inline layout should preserve the beginning of a long final assistant reply')
    assert.equal(longOutput.includes('long-line-20'), true, 'default inline layout should preserve the end of a long final assistant reply')
    assert.equal(longOutput.includes('lines above latest'), false, 'default inline layout should use terminal natural scroll, not the fullscreen viewport marker')
  }
  if (fullscreenLayout) {
    const beforeScroll = stdout.content.length
    stdin.press('\u001B[5~')
    await waitForOutputAfter(stdout, 'lines above latest', beforeScroll)
    const beforeScrollBack = stdout.content.length
    stdin.press('\u001B[6~')
    await settle()
    assert.equal(stdout.content.slice(beforeScrollBack).includes('lines above latest'), false)
  }

  const beforeStreamScroll = stdout.content.length
  await clearPromptInput()
  stdin.press('stream scroll')
  await settle()
  stdin.press('\r')
  await waitForOutputAfter(stdout, 'stream-line-12', beforeStreamScroll)
  assert.equal(stdout.content.slice(beforeStreamScroll).includes('lines above latest'), false, 'default live streaming should stay pinned until the user requests app scroll')
  await waitForOutputAfter(stdout, 'earlier messages hidden', beforeStreamScroll)
  if (!fullscreenLayout) {
    assert.equal(stdout.content.slice(beforeStreamScroll).includes('\u001B[?1000h'), true, 'live streaming should enable terminal wheel tracking before app scroll is active')
  }
  const beforeLiveScroll = stdout.content.length
  stdin.press('\u001B[<64;10;5M')
  await waitForOutputAfter(stdout, 'lines above latest', beforeLiveScroll)
  await waitForOutputAfter(stdout, 'new output below', beforeLiveScroll)
  const mouseTrackingOutput = fullscreenLayout ? stdout.content : stdout.content.slice(beforeStreamScroll)
  assert.equal(mouseTrackingOutput.includes('\u001B[?1000h'), true, 'app-level scroll should enable terminal wheel tracking')
  const beforeWheel = stdout.content.length
  stdin.press('\u001B[<68;10;5M')
  await settle()
  assert.equal(stdout.content.slice(beforeWheel).includes('[<68;10;5M'), false, 'modified mouse wheel events should scroll history instead of leaking into the prompt')
  await settle(1000)
  const liveScrolledOutput = stdout.content.slice(beforeLiveScroll)
  assert.equal(liveScrolledOutput.includes('stream-line-30'), false, 'streaming should not snap back to the newest line while the user is scrolled up')
  assert.equal(stdout.content.slice(beforeLiveScroll).includes('blocks hidden'), false, 'live assistant output should scroll as content, not collapse behind ctrl+o')
  const beforeResize = stdout.content.length
  stdout.resize(64, 22)
  await waitForOutputAfter(stdout, 'lines above latest', beforeResize)
  await waitForOutputAfter(stdout, 'ask or type / for commands', beforeResize)
  assert.equal(stdout.content.slice(beforeResize).includes('blocks hidden'), false, 'resizing while scrolled should preserve visible content instead of folding it')
  stdout.resize(100, 30)
  await settle()
  await waitForOutputAfter(stdout, 'done', beforeStreamScroll)
  const beforeAfterDoneResize = stdout.content.length
  stdout.resize(88, 24)
  await waitForOutputAfter(stdout, 'lines above latest', beforeAfterDoneResize)
  const beforeDoneScrollBack = stdout.content.length
  stdin.press('\u001B[6;2~')
  for (let index = 0; index < 8; index++) stdin.press('\u001B[6~')
  await settle()
  assert.equal(stdout.content.slice(beforeDoneScrollBack).includes('lines above latest'), false, 'page down after a finished stream should return to the natural bottom layout')
  if (!fullscreenLayout) {
    assert.equal(stdout.content.slice(beforeDoneScrollBack).includes('\u001B[?1000l'), true, 'returning to natural bottom layout should release terminal mouse tracking')
  }
  stdout.resize(100, 30)
  await settle()

  const beforeDoneOnly = stdout.content.length
  await clearPromptInput()
  stdin.press('done only')
  await settle()
  stdin.press('\r')
  await waitForOutputAfter(stdout, 'done only answer', beforeDoneOnly)
  await waitForOutputAfter(stdout, 'done', beforeDoneOnly)

  const beforeErrorTurn = stdout.content.length
  await clearPromptInput()
  stdin.press('error turn')
  await settle()
  stdin.press('\r')
  await waitForOutputAfter(stdout, 'fixture runtime exploded', beforeErrorTurn)
  await waitForOutputAfter(stdout, 'stopped', beforeErrorTurn)

  const beforeLoopExceeded = stdout.content.length
  await clearPromptInput()
  stdin.press('loop exceeded')
  await settle()
  stdin.press('\r')
  await waitForOutputAfter(stdout, 'tool loop stopped', beforeLoopExceeded)
  await waitForOutputAfter(stdout, 'configured max_tool_iterations limit', beforeLoopExceeded)
  await waitForOutputAfter(stdout, 'stopped', beforeLoopExceeded)

  const beforeAfterFailure = stdout.content.length
  await clearPromptInput()
  stdin.press('after failure')
  await settle()
  stdin.press('\r')
  await waitForOutputAfter(stdout, 'fixture answer: after failure', beforeAfterFailure)
  await waitForOutputAfter(stdout, 'done', beforeAfterFailure)

  const beforeApproval = stdout.content.length
  await clearPromptInput()
  stdin.press('approval please')
  await settle()
  stdin.press('\r')
  await waitForOutputAfter(stdout, 'Permission Request', beforeApproval)
  await settle(120)
  stdin.press('y')
  await waitForOutputAfter(stdout, 'fixture approval granted', beforeApproval)
  await waitForOutputAfter(stdout, 'done', beforeApproval)

  stdin.press('slow turn')
  await settle()
  stdin.press('\r')
  await waitForOutput(stdout, 'working slowly')
  const beforeBusyInput = stdout.content.length
  stdin.press('queued after run')
  await settle()
  assert.match(
    stdout.content.slice(beforeBusyInput),
    /\u001B\[3A\u001B\[[0-9]+G/,
    'app prompt cursor should remain anchored on the textbox content row while a turn is streaming'
  )
  stdin.press('\r')
  await waitForOutput(stdout, 'queued after run')
  await waitForOutput(stdout, 'fixture answer: queued after run')

  stdin.press('interruptible turn')
  await settle()
  stdin.press('\r')
  await waitForOutput(stdout, 'Tool Running')
  stdin.press('queued after interrupt')
  await settle()
  stdin.press('\r')
  await waitForOutput(stdout, 'cancelable tools interrupted')
  await waitForOutput(stdout, 'canceled')
  await waitForOutput(stdout, 'fixture answer: queued after interrupt')

  stdin.press('hang turn')
  await settle()
  stdin.press('\r')
  await waitForOutput(stdout, 'working until cancelled')
  stdin.press('/cancel')
  await settle()
  stdin.press('\r')
  await waitForOutput(stdout, 'interrupt')
  await waitForOutput(stdout, 'cancelled')

  stdin.press('/exit')
  await settle()
  stdin.press('\r')
  await waitUntilExit(instance, stdout)

  assert.deepEqual(consoleMessages, [])
  assert.equal(stderr.content.trim(), '')
  console.log('terminal app flow smoke passed')
} finally {
  console.warn = originalWarn
  console.error = originalError
  instance?.unmount()
  instance?.cleanup()
}
