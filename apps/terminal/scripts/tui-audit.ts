import {spawnSync} from 'node:child_process'
import path from 'node:path'

type Task = {
  label: string
  executable?: string
  cwd?: string
  args: string[]
  env?: NodeJS.ProcessEnv
}

const terminalRoot = process.cwd()
const repoRoot = path.resolve(terminalRoot, '../..')
const verifyManual = process.argv.includes('--verify-manual')
const manualReportPath = valueAfter('--report-path')

const terminalTasks: Task[] = [
  {label: 'typecheck', args: ['run', 'typecheck']},
  {label: 'render-smoke', args: ['run', 'render-smoke']},
  {label: 'interaction-smoke', args: ['run', 'interaction-smoke']},
  {label: 'app-smoke', args: ['run', 'app-smoke']},
  {label: 'app-compact-smoke', args: ['run', 'app-compact-smoke']},
  {label: 'app-short-smoke', args: ['run', 'app-short-smoke']},
  {label: 'app-narrow-smoke', args: ['run', 'app-narrow-smoke']},
  {label: 'app-tiny-smoke', args: ['run', 'app-tiny-smoke']},
  {label: 'app-tiny-fullscreen-smoke', args: ['run', 'app-tiny-fullscreen-smoke']},
  {label: 'app-flow-smoke', args: ['run', 'app-flow-smoke']},
  {label: 'app-compact-flow-smoke', args: ['run', 'app-compact-flow-smoke']},
  {label: 'app-short-fullscreen-flow-smoke', args: ['run', 'app-short-fullscreen-flow-smoke']},
  {label: 'app-fullscreen-smoke', args: ['run', 'app-fullscreen-smoke']},
  {label: 'app-compact-fullscreen-smoke', args: ['run', 'app-compact-fullscreen-smoke']},
  {label: 'app-inline-smoke', args: ['run', 'app-inline-smoke']},
  {label: 'app-pending-resume-smoke', args: ['run', 'app-pending-resume-smoke']},
  {label: 'manual-smoke-check', args: ['run', 'manual-smoke:check']}
]

const runtimeTasks: Task[] = [
  {
    label: 'ts-core-tests',
    cwd: repoRoot,
    args: ['test', 'packages/host/test/corePackage.test.ts']
  }
]

const repoTasks: Task[] = [
  {
    label: 'git-diff-check',
    executable: 'git',
    cwd: repoRoot,
    args: ['diff', '--check']
  }
]

const manualTasks: Task[] = verifyManual
  ? [{label: 'manual-smoke-verify', args: ['run', 'manual-smoke:verify', ...(manualReportPath ? ['--report-path', manualReportPath] : [])]}]
  : []

for (const task of [...manualTasks, ...terminalTasks, ...runtimeTasks, ...repoTasks]) runTask(task)

if (!verifyManual) {
  console.log('')
  console.log('manual smoke report not verified; run `make manual-smoke` or `make terminal-manual-smoke` in a real terminal, then `make terminal-audit-complete` for the final gate')
}
console.log('')
console.log('terminal TUI audit passed')

function runTask(task: Task): void {
  const executable = task.executable ?? process.execPath
  console.log(`\n== ${task.label} ==`)
  const result = spawnSync(executable, task.args, {
    cwd: task.cwd ?? terminalRoot,
    env: task.env ?? process.env,
    stdio: 'inherit'
  })
  if (result.status !== 0) {
    console.error(`\n${task.label} failed with exit code ${result.status ?? 'unknown'}`)
    process.exit(result.status ?? 1)
  }
}

function valueAfter(flag: string): string | undefined {
  const index = process.argv.indexOf(flag)
  return index >= 0 ? process.argv[index + 1] : undefined
}
