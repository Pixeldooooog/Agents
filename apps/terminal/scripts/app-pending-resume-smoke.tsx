import assert from 'node:assert/strict'
import {mkdir, writeFile} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import path from 'node:path'
import {Readable, Writable} from 'node:stream'
import React from 'react'
import {render, type Instance, type RenderOptions} from 'ink'
import {App} from '../src/app/App.js'

const repoRoot = path.resolve(process.cwd(), '../..')
const sessionRoot = path.join(tmpdir(), `agents-terminal-pending-sessions-${process.pid}`)
process.env.AGENTS_TERMINAL_HISTORY_PATH = path.join(tmpdir(), `agents-terminal-pending-history-${process.pid}.json`)
process.env.AGENTS_TERMINAL_SESSION_STORE = sessionRoot
process.env.AGENTS_TERMINAL_DB_PATH = path.join(tmpdir(), `agents-terminal-pending-${process.pid}.db`)

async function waitForOutput(output: TestOutput, expected: string, timeoutMs = 5000): Promise<void> {
  const startedAt = Date.now()
  while (!output.content.includes(expected)) {
    if (Date.now() - startedAt > timeoutMs) {
      throw new Error(`timed out waiting for ${expected}; output was:\n${output.content.slice(-2500)}`)
    }
    await settle(40)
  }
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
}

const stdin = new TestInput()
const stdout = new TestOutput()
const stderr = new TestOutput()
const consoleMessages: string[] = []
const originalWarn = console.warn
const originalError = console.error
let instance: Instance | undefined

try {
  await seedPendingSession()
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

  await waitForOutput(stdout, 'Agents Code')
  stdin.press('/resume')
  await settle()
  stdin.press('\r')
  await waitForOutput(stdout, 'Resume Session')
  stdin.press('\r')
  await waitForOutput(stdout, 'Permission Request')
  await waitForOutput(stdout, 'filesystem.write')
  await waitForOutput(stdout, 'pending approval smoke')

  assert.deepEqual(consoleMessages, [])
  assert.equal(stderr.content.trim(), '')
  console.log('terminal pending resume smoke passed')
} finally {
  console.warn = originalWarn
  console.error = originalError
  instance?.unmount()
  instance?.cleanup()
}

async function seedPendingSession(): Promise<void> {
  await mkdir(sessionRoot, {recursive: true})
  const call = {id: 'call-pending', name: 'filesystem.write', arguments: {path: 'pending.txt', content: 'ok'}}
  const approval = {
    type: 'tool_approval_required',
    name: 'filesystem.write',
    payload: {
      approval_id: 'call-pending',
      tool_call: call,
      impact: {risk: 'medium'},
      permission: {reason: 'pending approval smoke'}
    }
  }
  const messages = [
    {role: 'system', content: [{type: 'text', text: 'system prompt'}]},
    {role: 'user', content: [{type: 'text', text: 'write pending file'}]},
    {role: 'assistant', content: [], tool_calls: [call]}
  ]
  await writeFile(
    path.join(sessionRoot, 'session-pending.json'),
    JSON.stringify({
      session_id: 'session-pending',
      updated_at: Date.now() / 1000,
      profile: 'coding',
      model: 'scripted · pending',
      workspace_path: repoRoot,
      messages,
      pending_run_id: 'run-pending',
      pending_approval: approval,
      checkpoint: {
        run_id: 'run-pending',
        step: 'approval_required',
        iteration: 0,
        messages,
        tool_results: [],
        events: [approval],
        pending_tool_calls: [call],
        tool_approvals: {},
        tool_approval_scopes: {},
        tool_approval_grants: {},
        created_at: Date.now() / 1000
      }
    }, null, 2),
    'utf8'
  )
}
