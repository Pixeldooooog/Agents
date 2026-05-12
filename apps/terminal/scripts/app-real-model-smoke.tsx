import assert from 'node:assert/strict'
import {tmpdir} from 'node:os'
import path from 'node:path'
import {Readable, Writable} from 'node:stream'
import React from 'react'
import {render, type Instance, type RenderOptions} from 'ink'
import {App} from '../src/App.js'

const repoRoot = path.resolve(process.cwd(), '../..')
const srcPath = path.join(repoRoot, 'src')
process.env.PYTHONPATH = [srcPath, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter)
process.env.AGENTS_TERMINAL_HISTORY_PATH = path.join(tmpdir(), `agents-terminal-real-history-${process.pid}.json`)
process.env.AGENTS_TERMINAL_SESSION_STORE = path.join(tmpdir(), `agents-terminal-real-sessions-${process.pid}`)
process.env.AGENTS_TERMINAL_DB_PATH = path.join(tmpdir(), `agents-terminal-real-${process.pid}.db`)

async function waitForOutput(output: TestOutput, expected: string, timeoutMs = 5000): Promise<void> {
  await waitForOutputAfter(output, expected, 0, timeoutMs)
}

async function waitForOutputAfter(output: TestOutput, expected: string, startIndex: number, timeoutMs = 5000): Promise<void> {
  const startedAt = Date.now()
  while (!output.content.slice(startIndex).includes(expected)) {
    if (Date.now() - startedAt > timeoutMs) {
      throw new Error(`timed out waiting for ${expected}; output was:\n${output.content.slice(-2500)}`)
    }
    await settle(80)
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
  console.warn = (...args: unknown[]) => consoleMessages.push(args.map(String).join(' '))
  console.error = (...args: unknown[]) => consoleMessages.push(args.map(String).join(' '))
  instance = render(
    <App python=".venv/bin/python" repoRoot={repoRoot} bridgeArgs={['--profile', 'chat', '--permission', 'auto']} />,
    {
      stdin,
      stdout,
      stderr,
      exitOnCtrlC: false,
      patchConsole: false
    } as unknown as RenderOptions
  )

  await waitForOutput(stdout, 'Agents Code')
  const marker = stdout.content.length
  stdin.press('Respond with the two-letter word represented by NATO letters Oscar Kilo and nothing else.')
  await settle()
  stdin.press('\r')
  await waitForOutputAfter(stdout, 'OK', marker, 60000)
  stdin.press('/exit')
  await settle()
  stdin.press('\r')
  await waitUntilExit(instance, stdout)

  assert.deepEqual(consoleMessages, [])
  assert.equal(stderr.content.trim(), '')
  console.log('terminal app real model smoke passed')
} finally {
  console.warn = originalWarn
  console.error = originalError
  instance?.unmount()
  instance?.cleanup()
}
