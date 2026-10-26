import {spawn, type ChildProcessWithoutNullStreams} from 'node:child_process'
import path from 'node:path'
import {createInterface} from 'node:readline'
import type {TerminalHostCommand, TerminalHostEvent} from './terminalHostProtocol.js'

export type TerminalHostClientOptions = {
  repoRoot: string
  args: string[]
  fixture?: boolean
}

export class TerminalHostClient {
  private child: ChildProcessWithoutNullStreams | null = null
  private shutdownTimer: NodeJS.Timeout | null = null
  private listeners = new Set<(event: TerminalHostEvent) => void>()

  constructor(private readonly options: TerminalHostClientOptions) {}

  onEvent(listener: (event: TerminalHostEvent) => void): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  start(): void {
    if (this.child) return
    const repoRoot = path.resolve(this.options.repoRoot)
    const terminalHostEntry = path.join(repoRoot, 'packages/host/src/terminal/main.ts')
    const child = spawn(process.execPath, ['run', terminalHostEntry, '--repo-root', repoRoot, ...this.options.args], {
      cwd: repoRoot,
      env: {...process.env, KEVIN_REPO_ROOT: repoRoot, ...(this.options.fixture ? {KEVIN_TERMINAL_FIXTURE: '1'} : {})},
      stdio: ['pipe', 'pipe', 'pipe']
    })
    this.child = child
    const lines = createInterface({input: child.stdout})
    lines.on('line', line => {
      if (!line.trim()) return
      try {
        this.emit(JSON.parse(line) as TerminalHostEvent)
      } catch (error) {
        this.emit({type: 'error', message: `invalid terminal host event: ${String(error)}`})
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
      if (code && code !== 0) this.emit({type: 'error', message: `terminal host exited with code ${code}`})
      this.emit({type: 'exit'})
    })
  }

  send(command: TerminalHostCommand): void {
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

  private emit(event: TerminalHostEvent): void {
    for (const listener of this.listeners) listener(event)
  }
}
