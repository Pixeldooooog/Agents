import assert from 'node:assert/strict'
import {execFileSync} from 'node:child_process'
import {mkdtemp, mkdir, rm, writeFile} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import path from 'node:path'
import {readWorkspaceFileIndex} from '../src/files/workspaceFileIndex.js'

const root = await mkdtemp(path.join(tmpdir(), 'agents-file-index-'))
try {
  execFileSync('git', ['init', '--quiet', root])
  const emptyGlobalIgnore = path.join(root, '.git', 'empty-global-ignore')
  await writeFile(emptyGlobalIgnore, '')
  execFileSync('git', ['config', '--local', 'core.excludesFile', emptyGlobalIgnore], {cwd: root})
  await writeFile(path.join(root, '.gitignore'), 'ignored-secret.txt\n')
  await writeFile(path.join(root, 'tracked.txt'), 'tracked')
  execFileSync('git', ['add', 'tracked.txt'], {cwd: root})
  for (const name of ['untracked.txt', ' name with spaces.txt', 'line\nbreak.txt', 'ignored-secret.txt']) {
    await writeFile(path.join(root, name), 'fixture')
  }
  await mkdir(path.join(root, 'logs'))
  await writeFile(path.join(root, 'logs', 'excluded.txt'), 'log')
  const files = await readWorkspaceFileIndex(root, {rgCommand: path.join(root, 'missing-rg')})
  assert(files.includes('tracked.txt'))
  assert(files.includes('untracked.txt'))
  assert(files.includes(' name with spaces.txt'))
  assert(files.includes('line\nbreak.txt'))
  assert(!files.includes('ignored-secret.txt'))
  assert(!files.includes('logs/excluded.txt'))
  assert(!files.some(file => file.startsWith('.git/')))
  console.log('terminal file index fallback smoke passed')
} finally {
  await rm(root, {recursive: true, force: true})
}
