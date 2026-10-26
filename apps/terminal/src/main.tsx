import React from 'react'
import {render} from 'ink'
import {App} from './app/App.js'

const args = parseArgs(process.argv.slice(2))

render(<App repoRoot={args.repoRoot} terminalHostArgs={args.terminalHostArgs} terminalHostFixture={args.terminalHostFixture} />)

function parseArgs(argv: string[]) {
  let repoRoot = process.env.KEVIN_REPO_ROOT || '..'
  let terminalHostFixture = process.env.KEVIN_TERMINAL_FIXTURE === '1'
  const terminalHostArgs: string[] = []
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index]
    if (value === '--repo-root') {
      repoRoot = argv[++index] ?? repoRoot
    } else if (value === '--terminal-host-fixture') {
      terminalHostFixture = Boolean(argv[++index] ?? true)
    } else {
      terminalHostArgs.push(value)
    }
  }
  return {repoRoot, terminalHostArgs, terminalHostFixture}
}
