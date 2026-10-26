import './interactive-test-environment.js'
import assert from 'node:assert/strict'
import {mkdir, rm, writeFile} from 'node:fs/promises'
import path from 'node:path'
import {Readable, Writable} from 'node:stream'
import React from 'react'
import {render, type Instance, type RenderOptions} from 'ink'
import {createAppSmokeWorkspace} from './fixtures/appSmokeWorkspace.js'
import {App} from '../src/app/App.js'
import {isFullscreenLayoutEnabled} from '../src/app/terminalLayout.js'

const repoRoot = await createAppSmokeWorkspace(path.resolve(import.meta.dir, '../../..'))
const terminalRows = Number(process.env.AGENTS_TERMINAL_ROWS ?? 30)
const terminalColumns = Number(process.env.AGENTS_TERMINAL_COLUMNS ?? 100)
const compactTerminal = terminalRows < 29 || terminalColumns < 80
const tinyTerminal = terminalColumns < 40
const fullscreenLayout = isFullscreenLayoutEnabled()
const promptReadyText = terminalColumns < 36 ? 'for commands' : 'ask or type / for commands'
process.env.AGENTS_TERMINAL_HISTORY_PATH = path.join(repoRoot, '.test-state', 'history.json')
process.env.AGENTS_TERMINAL_SESSION_STORE = path.join(repoRoot, '.test-state', 'sessions')
process.env.AGENTS_TERMINAL_DB_PATH = path.join(repoRoot, '.test-state', 'terminal.db')

async function waitForOutput(output: TestOutput, expected: string, timeoutMs = 5000): Promise<void> {
  const startedAt = Date.now()
  while (!output.content.includes(expected)) {
    if (Date.now() - startedAt > timeoutMs) {
      throw new Error(`timed out waiting for ${expected}; output was:\n${output.content.slice(-2000)}`)
    }
    await settle(40)
  }
}

async function waitForOutputAfter(output: TestOutput, expected: string, marker: number, timeoutMs = 5000): Promise<void> {
  const startedAt = Date.now()
  while (!output.content.slice(marker).includes(expected)) {
    if (Date.now() - startedAt > timeoutMs) {
      throw new Error(`timed out waiting for ${expected} after marker; output was:\n${output.content.slice(marker).slice(-2000)}`)
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
    new Promise((_resolve, reject) => setTimeout(() => reject(new Error(`timed out waiting for app exit; output was:\n${output.content.slice(-2000)}`)), timeoutMs))
  ])
}

function settle(ms = 40): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
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
  columns = Number.isFinite(terminalColumns) && terminalColumns > 0 ? terminalColumns : 100
  rows = Number.isFinite(terminalRows) && terminalRows > 0 ? terminalRows : 30
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
  await seedSessionStore(process.env.AGENTS_TERMINAL_SESSION_STORE)
  console.warn = (...args: unknown[]) => consoleMessages.push(args.map(String).join(' '))
  console.error = (...args: unknown[]) => consoleMessages.push(args.map(String).join(' '))
  instance = render(
    <App repoRoot={repoRoot} terminalHostArgs={[]} />,
    {
      stdin,
      stdout,
      stderr,
      exitOnCtrlC: false,
      patchConsole: false
    } as unknown as RenderOptions
  )

  if (compactTerminal) await waitForOutput(stdout, promptReadyText)
  else await waitForOutput(stdout, 'Agents Code')
  assert.equal(stdout.content.includes('● idle'), false, 'app should not render the old idle/model status line above the prompt')
  assert.equal(stdout.content.includes('folded'), false, 'app should not show folded state chrome in the prompt area')
  assert.match(stdout.content, /\u001B\[5 q/, 'App should switch the terminal cursor to a steady bar while mounted')
  assert.match(stdout.content, /\u001B\[\?2004h/, 'App should enable bracketed paste while mounted')
  if (fullscreenLayout) {
    assert.equal(stdout.content.includes('\u001B[?1000h'), true, 'fullscreen startup should enable app-level mouse scrolling')
  } else {
    assert.equal(stdout.content.includes('\u001B[?1000h'), false, 'inline startup should leave native terminal mouse scrolling alone')
  }
  if (!compactTerminal) {
    const beforeShrink = stdout.content.length
    stdout.resize(64, 18)
    await waitForOutputAfter(stdout, 'ask or type / for commands', beforeShrink)
    await settle()
    const shrinkOutput = stdout.content.slice(beforeShrink)
    assert.ok(
      shrinkOutput.lastIndexOf('ask or type / for commands') > shrinkOutput.lastIndexOf('Welcome back!'),
      'terminal resize should recalculate layout and end on the compact prompt instead of the wide welcome panel'
    )
    const beforeRestore = stdout.content.length
    stdout.resize(terminalColumns, terminalRows)
    await waitForOutputAfter(stdout, 'Agents Code', beforeRestore)
    const beforePromptResize = stdout.content.length
    stdin.press('resize prompt 你好世界你好世界')
    await settle()
    stdout.resize(64, 18)
    await waitForOutputAfter(stdout, 'resize prompt', beforePromptResize)
    assert.ok(
      stdout.content.slice(beforePromptResize).lastIndexOf('resize prompt') > stdout.content.slice(beforePromptResize).lastIndexOf('Welcome back!'),
      'terminal resize while editing should keep the active input visible instead of leaving welcome layout residue at the bottom'
    )
    stdin.press('\u0003')
    await settle()
    stdout.resize(terminalColumns, terminalRows)
    await settle()
  }
  if (tinyTerminal) {
    const beforeTinySuggestions = stdout.content.length
    stdin.press('/')
    await settle()
    assert.equal(stdout.content.slice(beforeTinySuggestions).includes('Comman'), false, 'tiny terminals should hide the command panel instead of rendering a broken suggestion box')
    stdin.press('\u001B')
    await settle()
    stdin.press('/status\r')
    await waitForOutput(stdout, 'Status')
  } else {
    stdin.press('/')
    await waitForOutput(stdout, 'Commands')
    stdin.press('\u001B')
    await settle()
    stdin.press('@apps/terminal/package')
    await waitForOutput(stdout, 'Files')
    await waitForOutput(stdout, 'apps/terminal/package.json')
    stdin.press('\u001B')
    await settle()
    stdin.press('/status')
    await settle()
    stdin.press('\r')
    await waitForOutput(stdout, 'Status')
    stdin.press('/sessions')
    await settle()
    stdin.press('\r')
    await waitForOutput(stdout, 'Sessions')
    stdin.press('/resume')
    await settle()
    stdin.press('\r')
    await waitForOutput(stdout, 'Resume Session')
    await settle()
    if (compactTerminal) {
      stdin.press('\u001B')
    } else {
      stdin.press('\r')
      await waitForOutput(stdout, 'hello from saved session')
      stdin.press('\u001B')
    }
    await settle(250)
    stdin.press('\u001Bp')
    await waitForOutput(stdout, 'Model Profiles')
    await settle()
    stdin.press('\r')
    await waitForOutput(stdout, 'model switched to')
  }
  await settle(250)
  stdin.press('/exit')
  await settle()
  stdin.press('\r')
  await waitUntilExit(instance, stdout)

  assert.deepEqual(consoleMessages, [])
  assert.equal(stderr.content.trim(), '')
  console.log('terminal app smoke passed')
} finally {
  console.warn = originalWarn
  console.error = originalError
  instance?.unmount()
  instance?.cleanup()
  await rm(repoRoot, {recursive: true, force: true})
}

async function seedSessionStore(root: string): Promise<void> {
  await mkdir(root, {recursive: true})
  await writeFile(
    path.join(root, 'session-smoke.json'),
    JSON.stringify({
      session_id: 'session-smoke',
      updated_at: Date.now() / 1000,
      profile: 'coding',
      model: 'openai-chat · fixture-model',
      workspace_path: repoRoot,
      messages: [
        {role: 'system', content: [{type: 'text', text: 'saved system prompt'}]},
        {role: 'user', content: [{type: 'text', text: 'hello from saved session'}]}
      ]
    }, null, 2),
    'utf8'
  )
}
