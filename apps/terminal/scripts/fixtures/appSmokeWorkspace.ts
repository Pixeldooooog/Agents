import {execFileSync} from 'node:child_process'
import {mkdir, mkdtemp, rm, symlink, writeFile} from 'node:fs/promises'
import {tmpdir} from 'node:os'
import path from 'node:path'

/** Runs real Host code against disposable config/data, never the developer's .env. */
export async function createAppSmokeWorkspace(sourceRoot: string): Promise<string> {
  const root = await mkdtemp(path.join(tmpdir(), 'kevin-app-smoke-'))
  try {
    await symlink(path.join(sourceRoot, 'packages'), path.join(root, 'packages'), 'dir')
    await mkdir(path.join(root, 'apps', 'terminal'), {recursive: true})
    await writeFile(path.join(root, 'apps', 'terminal', 'package.json'), '{"name":"terminal-smoke-fixture"}\n')
    await writeFile(path.join(root, '.env'), [
      'OPENAI_API_KEY=fixture-not-a-credential',
      'OPENAI_MODEL=fixture-model',
      'OPENAI_BASE_URL=http://127.0.0.1:1/v1',
      'AGENT_MODEL_PROFILES=',
      'KEVIN_TERMINAL_FIXTURE=1',
      ''
    ].join('\n'))
    await writeFile(path.join(root, '.gitignore'), '.env\n.test-state/\n')
    execFileSync('git', ['init', '--quiet', root])
    const emptyGlobalIgnore = path.join(root, '.git', 'empty-global-ignore')
    await writeFile(emptyGlobalIgnore, '')
    execFileSync('git', ['config', '--local', 'core.excludesFile', emptyGlobalIgnore], {cwd: root})
    return root
  } catch (error) {
    await rm(root, {recursive: true, force: true})
    throw error
  }
}
