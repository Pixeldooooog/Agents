import {spawn} from 'node:child_process'
import {readFileSync, writeFileSync} from 'node:fs'
import path from 'node:path'
import {stdin as input, stdout as output} from 'node:process'
import {createInterface} from 'node:readline/promises'

const repoRoot = path.resolve(process.cwd(), '../..')
const printOnly = process.argv.includes('--print-only')
const record = process.argv.includes('--record')
const verify = process.argv.includes('--verify')
const reportPath = valueAfter('--report-path') ?? '/tmp/agents-terminal-manual-smoke-report.json'
const reportApp = 'apps/terminal'
const reportCommand = 'bun run --cwd apps/terminal manual-smoke:record'

const checklist = [
  '1. Type Chinese text in the boxed prompt; the IME preedit/candidate window should follow the prompt cursor.',
  '2. Type enough mixed Chinese/ASCII text to wrap; the native cursor should stay inside the prompt row while editing.',
  '3. Use Shift+Enter between two lines, then Enter; the submitted message should preserve the newline.',
  '4. Type a draft and press Ctrl+L; the visible transcript should clear while the draft stays editable.',
  '5. Submit "stream scroll"; during streaming, scroll up with the trackpad or mouse wheel.',
  '6. While scrolled up, output should not snap to the newest line and should show "new output below".',
  '7. Scroll/PageDown back to latest; the app should return to the natural bottom layout after the stream finishes.',
  '8. Resize the terminal while editing and while scrolled up; the prompt and viewport should stay coherent.',
  '9. Try selecting transcript text during idle and during streaming; note if the terminal requires Shift/Option selection.',
  '10. Type /exit to quit.'
]

if (verify) verifyReport(reportPath)

if (record && !input.isTTY && !printOnly) {
  console.error('manual smoke record requires a real TTY; run `make manual-smoke` or `make terminal-manual-smoke` in your terminal.')
  process.exit(1)
}

console.log('Terminal manual smoke checklist')
console.log('')
for (const item of checklist) console.log(item)
console.log('')

if (printOnly) process.exit(0)

if (record) {
  console.log(`Recording manual smoke report to ${reportPath}`)
  console.log('This recorder runs the fixture TUI first. Type /exit when done, then answer p/f/s prompts to write the report.')
  console.log('A normal make terminal session does not create this report.')
  console.log('')
}

const child = spawn(
  process.execPath,
  ['run', 'src/main.tsx', '--repo-root', repoRoot, '--terminal-host-fixture', 'fixture'],
  {
    cwd: path.join(repoRoot, 'apps/terminal'),
    env: {
      ...process.env,
      AGENTS_TERMINAL_FIXTURE: '1',
      AGENTS_TERMINAL_HISTORY_PATH: '/tmp/agents-terminal-manual-history.json',
      AGENTS_TERMINAL_SESSION_STORE: '/tmp/agents-terminal-manual-sessions'
    },
    stdio: 'inherit'
  }
)

child.on('exit', code => {
  if (!record) {
    process.exit(code ?? 0)
    return
  }
  void recordChecklist(code ?? 0)
})

async function recordChecklist(childCode: number) {
  if (!input.isTTY) {
    console.log('manual smoke record skipped: stdin is not a TTY')
    process.exit(childCode || 1)
  }
  const rl = createInterface({input, output})
  const results: Array<{check: string; status: 'pass' | 'fail' | 'skip'}> = []
  try {
    console.log('')
    console.log('Record manual smoke result')
    console.log('Enter p=pass, f=fail, s=skip for each item.')
    console.log('')
    for (const check of checklist) {
      let status: 'pass' | 'fail' | 'skip' | undefined
      while (!status) {
        const answer = (await rl.question(`${check}\n[p/f/s] `)).trim().toLowerCase()
        if (answer === 'p' || answer === 'pass') status = 'pass'
        else if (answer === 'f' || answer === 'fail') status = 'fail'
        else if (answer === 's' || answer === 'skip') status = 'skip'
      }
      results.push({check, status})
    }
  } finally {
    rl.close()
  }
  const report = {
    created_at: new Date().toISOString(),
    app: reportApp,
    command: reportCommand,
    passed: childCode === 0 && results.every(item => item.status === 'pass'),
    child_exit_code: childCode,
    results
  }
  writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`)
  console.log('')
  console.log(`manual smoke report: ${reportPath}`)
  process.exit(report.passed ? 0 : 1)
}

function valueAfter(flag: string): string | undefined {
  const index = process.argv.indexOf(flag)
  return index >= 0 ? process.argv[index + 1] : undefined
}

function verifyReport(pathname: string): never {
  let report: unknown
  try {
    report = JSON.parse(readFileSync(pathname, 'utf8'))
  } catch (error) {
    console.error(`manual smoke report could not be read: ${pathname}`)
    console.error(String(error))
    console.error('Run `make manual-smoke` or `make terminal-manual-smoke` in a real terminal, then rerun `make terminal-audit-complete`.')
    process.exit(1)
  }
  if (!isManualReport(report)) {
    console.error(`manual smoke report has an invalid shape: ${pathname}`)
    process.exit(1)
  }
  const failures = report.results.filter(item => item.status !== 'pass')
  const checklistMismatch = report.results.length !== checklist.length || report.results.some((item, index) => item.check !== checklist[index])
  const metadataMismatch = report.app !== reportApp || report.command !== reportCommand || Number.isNaN(Date.parse(report.created_at))
  if (report.child_exit_code !== 0) console.error(`manual smoke child exited with code ${report.child_exit_code}`)
  if (checklistMismatch) console.error('manual smoke report checklist does not match the current checklist')
  if (report.app !== reportApp) console.error(`manual smoke report app mismatch: ${report.app}`)
  if (report.command !== reportCommand) console.error(`manual smoke report command mismatch: ${report.command}`)
  if (Number.isNaN(Date.parse(report.created_at))) console.error(`manual smoke report created_at is invalid: ${report.created_at}`)
  for (const item of failures) console.error(`${item.status}: ${item.check}`)
  if (!report.passed || report.child_exit_code !== 0 || checklistMismatch || metadataMismatch || failures.length) {
    console.error(`manual smoke verification failed: ${pathname}`)
    process.exit(1)
  }
  console.log(`manual smoke verification passed: ${pathname}`)
  process.exit(0)
}

function isManualReport(value: unknown): value is {
  created_at: string
  app: string
  command: string
  passed: boolean
  child_exit_code: number
  results: Array<{check: string; status: 'pass' | 'fail' | 'skip'}>
} {
  if (!value || typeof value !== 'object') return false
  const report = value as Record<string, unknown>
  if (
    typeof report.created_at !== 'string' ||
    typeof report.app !== 'string' ||
    typeof report.command !== 'string' ||
    typeof report.passed !== 'boolean' ||
    typeof report.child_exit_code !== 'number' ||
    !Array.isArray(report.results)
  ) return false
  return report.results.every(item => {
    if (!item || typeof item !== 'object') return false
    const result = item as Record<string, unknown>
    return typeof result.check === 'string' && (result.status === 'pass' || result.status === 'fail' || result.status === 'skip')
  })
}
