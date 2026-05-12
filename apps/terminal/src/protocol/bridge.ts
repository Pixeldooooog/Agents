import {spawn, type ChildProcessWithoutNullStreams} from 'node:child_process'
import path from 'node:path'
import {createInterface} from 'node:readline'
import type {BridgeCommand, BridgeEvent} from './types.js'

export type BridgeOptions = {
  python: string
  repoRoot: string
  args: string[]
  module?: string
}

export class BridgeClient {
  private child: ChildProcessWithoutNullStreams | null = null
  private shutdownTimer: NodeJS.Timeout | null = null
  private listeners = new Set<(event: BridgeEvent) => void>()

  constructor(private readonly options: BridgeOptions) {}

  onEvent(listener: (event: BridgeEvent) => void): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  start(): void {
    if (this.child) return
    const repoRoot = path.resolve(this.options.repoRoot)
    const python = path.isAbsolute(this.options.python)
      ? this.options.python
      : path.resolve(repoRoot, this.options.python)
    const moduleName = this.options.module || 'agents.interfaces.bridge.ndjson'
    const child = spawn(python, ['-m', moduleName, ...this.options.args], {
      cwd: repoRoot,
      env: process.env,
      stdio: ['pipe', 'pipe', 'pipe']
    })
    this.child = child
    const lines = createInterface({input: child.stdout})
    lines.on('line', line => {
      if (!line.trim()) return
      try {
        this.emit(JSON.parse(line) as BridgeEvent)
      } catch (error) {
        this.emit({type: 'error', message: `invalid bridge event: ${String(error)}`})
      }
    })
    child.stderr.on('data', chunk => {
      const message = String(chunk).trim()
      if (message) this.emit({type: 'error', message})
    })
    child.on('exit', code => {
      if (this.child === child) this.child = null
      if (this.shutdownTimer) {
        clearTimeout(this.shutdownTimer)
        this.shutdownTimer = null
      }
      if (code && code !== 0) this.emit({type: 'error', message: `bridge exited with code ${code}`})
      this.emit({type: 'exit'})
    })
  }

  send(command: BridgeCommand): void {
    if (!this.child) return
    this.child.stdin.write(`${JSON.stringify(command)}\n`)
  }

  stop(): void {
    const child = this.child
    if (!child) return
    this.send({type: 'exit'})
    if (this.shutdownTimer) clearTimeout(this.shutdownTimer)
    this.shutdownTimer = setTimeout(() => {
      if (this.child === child) child.kill()
    }, 750)
    this.shutdownTimer.unref?.()
  }

  private emit(event: BridgeEvent): void {
    for (const listener of this.listeners) listener(event)
  }
}
