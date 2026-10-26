import {execFile} from 'node:child_process'
import {promisify} from 'node:util'

const execFileAsync = promisify(execFile)
const ignoredPathParts = new Set(['.git', 'node_modules', 'nexus-code', 'reference', 'artifacts', 'logs'])

/** Git fallback preserves ignored-file filtering when optional ripgrep is unavailable. */
export async function readWorkspaceFileIndex(cwd: string, options: {rgCommand?: string} = {}): Promise<string[]> {
  let output: string
  try {
    output = await listFiles(options.rgCommand ?? 'rg', ['--files', '--hidden', '--null'], cwd)
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error
    output = await listFiles('git', ['ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd)
  }
  return [...new Set(output.split('\0').filter(value => value && !value.split('/').some(part => ignoredPathParts.has(part))))]
}

async function listFiles(command: string, args: string[], cwd: string): Promise<string> {
  try {
    const {stdout} = await execFileAsync(command, args, {cwd, encoding: 'utf8', timeout: 5000, maxBuffer: 8 * 1024 * 1024})
    return stdout
  } catch (error) {
    // ripgrep returns 1 when there are no matching files; Git's errors must propagate.
    if (args[0] === '--files' && (error as {code?: unknown}).code === 1) return ''
    throw error
  }
}
