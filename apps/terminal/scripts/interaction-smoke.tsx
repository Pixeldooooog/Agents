import assert from 'node:assert/strict'
import {Readable, Writable} from 'node:stream'
import React from 'react'
import {render, type Instance, type RenderOptions} from 'ink'
import {ModelPicker} from '../src/components/ModelPicker.js'
import {PromptInput} from '../src/components/PromptInput.js'
import {Select, type SelectOption} from '../src/components/design/Select.js'
import {PermissionOptions} from '../src/components/permissions/PermissionOptions.js'
import {parseMouseEvent, parseNavigationEvent, splitTerminalControlEvents} from '../src/hooks/terminalInputParser.js'
import {isModelProfileQuery, modelProfileMatches} from '../src/ui/modelProfiles.js'
import {charLength, displayWidth, isBackspaceInput, isDeleteInput, nextWordBoundary, padDisplayEnd, previousWordBoundary} from '../src/ui/textBuffer.js'

const mounted: Instance[] = []
const consoleMessages: string[] = []
const originalWarn = console.warn
const originalError = console.error

async function smokeSelectArrowNavigation(): Promise<void> {
  const stdin = new TestInput()
  const selected: string[] = []
  mount(
    <Select options={options()} onSelect={value => selected.push(value)} />,
    stdin
  )

  await settle()
  stdin.press('\u001B[B')
  await settle()
  stdin.press('\r')
  await settle()

  assert.deepEqual(selected, ['beta'])
}

async function smokeSelectLineFeedSubmits(): Promise<void> {
  const stdin = new TestInput()
  const selected: string[] = []
  mount(
    <Select options={options()} onSelect={value => selected.push(value)} />,
    stdin
  )

  await settle()
  stdin.press('\n')
  await settle()

  assert.deepEqual(selected, ['alpha'])
}

async function smokeSelectFilter(): Promise<void> {
  const stdin = new TestInput()
  const selected: string[] = []
  mount(
    <Select options={options()} onSelect={value => selected.push(value)} filterable />,
    stdin
  )

  await settle()
  stdin.press('ga')
  await settle()
  stdin.press('\r')
  await settle()

  assert.deepEqual(selected, ['gamma'])
}

async function smokeSelectFilterDeleteKeyEditsQuery(): Promise<void> {
  const stdin = new TestInput()
  const selected: string[] = []
  mount(
    <Select options={options()} onSelect={value => selected.push(value)} filterable />,
    stdin
  )

  await settle()
  stdin.press('alpz')
  stdin.press('\u007F')
  await settle()
  stdin.press('\r')
  await settle()

  assert.deepEqual(selected, ['alpha'])
}

async function smokeSelectFilterDeleteEscapeSequenceEditsQuery(): Promise<void> {
  const stdin = new TestInput()
  const selected: string[] = []
  mount(
    <Select options={options()} onSelect={value => selected.push(value)} filterable />,
    stdin
  )

  await settle()
  stdin.press('betz')
  stdin.press('\u001B[3~')
  await settle()
  stdin.press('\r')
  await settle()

  assert.deepEqual(selected, ['beta'])
}

async function smokeSelectEscapeBehavior(): Promise<void> {
  const stdin = new TestInput()
  let cancelCount = 0
  mount(
    <Select options={options()} onSelect={() => undefined} onCancel={() => cancelCount++} filterable />,
    stdin
  )

  await settle()
  stdin.press('al')
  await settle()
  stdin.press('\u001B')
  await settle(80)
  assert.equal(cancelCount, 0)

  stdin.press('\u001B')
  await settle(80)
  assert.equal(cancelCount, 1)
}

async function smokeEmptySelectCanCancel(): Promise<void> {
  const stdin = new TestInput()
  let cancelCount = 0
  mount(
    <Select options={[]} onSelect={() => undefined} onCancel={() => cancelCount++} filterable emptyLabel="No saved sessions" />,
    stdin
  )

  await settle()
  stdin.press('\u001B')
  await settle(80)
  assert.equal(cancelCount, 1)
}

async function smokeSelectClampsSelectionAfterOptionsShrink(): Promise<void> {
  const stdin = new TestInput()
  const selected: string[] = []
  const instance = mount(
    <Select options={options()} onSelect={value => selected.push(value)} />,
    stdin
  )

  await settle()
  stdin.press('\u001B[B')
  await settle()
  stdin.press('\u001B[B')
  await settle()
  instance.rerender(<Select options={options().slice(0, 1)} onSelect={value => selected.push(value)} />)
  await settle()
  stdin.press('\r')
  await settle()

  assert.deepEqual(selected, ['alpha'])
}

async function smokeSelectPageNavigation(): Promise<void> {
  const stdin = new TestInput()
  const selected: string[] = []
  mount(
    <Select options={manyOptions(8)} onSelect={value => selected.push(value)} maxVisible={3} />,
    stdin
  )

  await settle()
  stdin.press('\u001B[6~')
  await settle()
  stdin.press('\r')
  await settle()

  assert.deepEqual(selected, ['item-4'])
}

async function smokeSelectCtrlPNavigation(): Promise<void> {
  const stdin = new TestInput()
  const selected: string[] = []
  mount(
    <Select options={options()} onSelect={value => selected.push(value)} />,
    stdin
  )

  await settle()
  stdin.press('\u001B[B')
  await settle()
  stdin.press('\u0010')
  await settle()
  stdin.press('\r')
  await settle()

  assert.deepEqual(selected, ['alpha'])
}

async function smokePermissionShortcutsSelectDecision(): Promise<void> {
  const decisions: string[] = []
  const run = async (key: string) => {
    const stdin = new TestInput()
    mount(
      <PermissionOptions onDecision={decision => decisions.push(decision)} />,
      stdin
    )
    await settle()
    stdin.press(key)
    await settle()
  }

  await run('y')
  await run('r')
  await run('n')

  assert.deepEqual(decisions, ['allow_once', 'allow_for_run', 'deny'])
}

async function smokeModelPickerNavigation(): Promise<void> {
  const stdin = new TestInput()
  const selected: string[] = []
  let cancelCount = 0
  mount(
    <ModelPicker
      profiles={[
        {name: 'coding', protocol: 'openai-responses', model: 'gpt-5.4', configured: true, active: true},
        {name: 'local', protocol: 'ollama', model: 'llama3', configured: true}
      ]}
      onSelect={value => selected.push(value)}
      onCancel={() => cancelCount++}
    />,
    stdin
  )

  await settle()
  stdin.press('\u001B[B')
  await settle()
  stdin.press('\r')
  await settle()

  assert.deepEqual(selected, ['local'])

  const cancelInput = new TestInput()
  mount(
    <ModelPicker
      profiles={[
        {name: 'coding', protocol: 'openai-responses', model: 'gpt-5.4', configured: true, active: true},
        {name: 'local', protocol: 'ollama', model: 'llama3', configured: true}
      ]}
      onSelect={value => selected.push(value)}
      onCancel={() => cancelCount++}
    />,
    cancelInput
  )
  await settle()
  cancelInput.press('\u001B')
  await settle(80)

  assert.equal(cancelCount, 1)

  const pageInput = new TestInput()
  mount(
    <ModelPicker
      profiles={Array.from({length: 8}, (_, index) => ({
        name: `profile-${index + 1}`,
        protocol: 'openai-responses',
        model: `model-${index + 1}`,
        configured: true,
        active: index === 0
      }))}
      onSelect={value => selected.push(value)}
      onCancel={() => cancelCount++}
      maxVisible={3}
    />,
    pageInput
  )
  await settle()
  pageInput.press('\u001B[6~')
  await settle()
  pageInput.press('\r')
  await settle()

  assert.deepEqual(selected, ['local', 'profile-4'])
}

async function smokePromptEscapeCancelsOnlyWhenInputIsEmpty(): Promise<void> {
  const stdin = new TestInput()
  let cancelCount = 0
  mount(
    <PromptInput
      repoRoot="/tmp"
      history={[]}
      onSubmit={() => undefined}
      onExit={() => false}
      onCancel={() => {
        cancelCount++
        return true
      }}
    />,
    stdin
  )

  await settle()
  stdin.press('draft')
  await settle()
  stdin.press('\u001B')
  await settle(80)
  assert.equal(cancelCount, 0)

  stdin.press('\u001B')
  await settle(80)
  assert.equal(cancelCount, 1)
}

async function smokePromptNativeCursorAnchorsInsideTextbox(): Promise<void> {
  const stdin = new TestInput()
  const stdout = new TestOutput()
  const submitted: string[] = []
  mount(
    <PromptInput repoRoot="/tmp" history={[]} onSubmit={value => submitted.push(value)} onExit={() => false} />,
    stdin,
    stdout
  )

  await settle()
  stdin.press('\u001B[<0;10;5M')
  await settle()
  stdin.press('\r')
  await settle()
  assert.deepEqual(submitted, [], 'mouse click tracking events should not leak into prompt text')

  stdin.press('你好')
  await settle()

  const positions = Array.from(stdout.content.matchAll(/\u001B\[[0-9]+A\u001B\[[0-9]+G/g), match => match[0])
  assert.equal(positions.includes('\u001B[3A\u001B[5G'), true, 'empty prompt cursor should sit on the textbox content row')
  assert.equal(positions.includes('\u001B[3A\u001B[9G'), true, 'CJK input should advance the native cursor by display width inside the textbox')
}

function smokeSafeInputTerminalSequences(): void {
  assert.deepEqual(parseMouseEvent('\u001B[<64;10;5M'), {wheel: 'up'}, 'SGR wheel up should be parsed as scroll up')
  assert.deepEqual(parseMouseEvent('\u001B[<65;10;5M'), {wheel: 'down'}, 'SGR wheel down should be parsed as scroll down')
  assert.deepEqual(parseMouseEvent('\u001B[<68;10;5M'), {wheel: 'up'}, 'modified SGR wheel up should still be parsed as scroll up')
  assert.deepEqual(parseMouseEvent('\u001B[<0;10;5M'), {}, 'ordinary mouse press should be recognized but not treated as wheel input')
  assert.deepEqual(parseMouseEvent('\u001B[M`!!'), {wheel: 'up'}, 'X10 wheel up should be parsed as scroll up')
  assert.deepEqual(
    splitTerminalControlEvents('\u001B[<64;10;5M\u001B[<64;10;5M\u001B[<65;10;5M'),
    ['\u001B[<64;10;5M', '\u001B[<64;10;5M', '\u001B[<65;10;5M'],
    'trackpad bursts should be split into individual mouse wheel events'
  )
  assert.deepEqual(
    splitTerminalControlEvents('\u001B[5~\u001B[5~'),
    ['\u001B[5~', '\u001B[5~'],
    'repeated PageUp sequences should be split into individual navigation events'
  )
  assert.deepEqual(parseNavigationEvent('\u001B[5~'), {pageUp: true}, 'PageUp should be parsed from basic CSI sequence')
  assert.deepEqual(parseNavigationEvent('\u001B[6;2~'), {pageDown: true}, 'modified PageDown should be parsed from CSI sequence')
  assert.deepEqual(parseNavigationEvent('\u001B[1;2A'), {upArrow: true}, 'modified arrow up should be parsed from CSI sequence')
}

async function smokePromptNativeCursorWrapsInsideTextbox(): Promise<void> {
  const stdin = new TestInput()
  const stdout = new TestOutput()
  stdout.columns = 24
  mount(
    <PromptInput repoRoot="/tmp" history={[]} onSubmit={() => undefined} onExit={() => false} />,
    stdin,
    stdout
  )

  await settle()
  const beforeInput = stdout.content.length
  stdin.press('你好世界你好世界你好')
  await settle()

  const positions = Array.from(stdout.content.slice(beforeInput).matchAll(/\u001B\[[0-9]+A\u001B\[[0-9]+G/g), match => match[0])
  assert.equal(positions.includes('\u001B[3A\u001B[9G'), true, 'wrapped CJK input should keep the native cursor inside the textbox instead of drifting into the footer')
}

async function smokePromptHistorySearchTabAcceptsMatch(): Promise<void> {
  const stdin = new TestInput()
  const submitted: string[] = []
  mount(
    <PromptInput
      repoRoot="/tmp"
      history={['first prompt', 'deploy production']}
      onSubmit={value => submitted.push(value)}
      onExit={() => false}
    />,
    stdin
  )

  await settle()
  stdin.press('\u0012')
  await settle()
  stdin.press('dep')
  await settle()
  stdin.press('\t')
  await settle()
  stdin.press('\r')
  await settle()

  assert.deepEqual(submitted, ['deploy production'])
}

async function smokePromptHistorySearchEnterExecutesMatch(): Promise<void> {
  const stdin = new TestInput()
  const submitted: string[] = []
  mount(
    <PromptInput
      repoRoot="/tmp"
      history={['first prompt', 'deploy production']}
      onSubmit={value => submitted.push(value)}
      onExit={() => false}
    />,
    stdin
  )

  await settle()
  stdin.press('\u0012')
  await settle()
  stdin.press('dep')
  await settle()
  stdin.press('\r')
  await settle()

  assert.deepEqual(submitted, ['deploy production'])
}

async function smokePromptHistorySearchCtrlRCyclesMatches(): Promise<void> {
  const stdin = new TestInput()
  const submitted: string[] = []
  mount(
    <PromptInput
      repoRoot="/tmp"
      history={['deploy staging', 'deploy production']}
      onSubmit={value => submitted.push(value)}
      onExit={() => false}
    />,
    stdin
  )

  await settle()
  stdin.press('\u0012')
  await settle()
  stdin.press('deploy')
  await settle()
  stdin.press('\u0012')
  await settle()
  stdin.press('\r')
  await settle()

  assert.deepEqual(submitted, ['deploy staging'])
}

async function smokePromptHistorySearchCtrlCCancelsSearch(): Promise<void> {
  const stdin = new TestInput()
  const submitted: string[] = []
  let exitCount = 0
  mount(
    <PromptInput
      repoRoot="/tmp"
      history={['deploy production']}
      onSubmit={value => submitted.push(value)}
      onExit={() => {
        exitCount++
        return false
      }}
    />,
    stdin
  )

  await settle()
  stdin.press('draft')
  await settle()
  stdin.press('\u0012')
  await settle()
  stdin.press('dep')
  await settle()
  stdin.press('\u0003')
  await settle()
  stdin.press('\r')
  await settle()

  assert.equal(exitCount, 0)
  assert.deepEqual(submitted, ['draft'])
}

async function smokePromptCtrlPNNavigateHistory(): Promise<void> {
  const stdin = new TestInput()
  const submitted: string[] = []
  mount(
    <PromptInput
      repoRoot="/tmp"
      history={['first prompt', 'second prompt']}
      onSubmit={value => submitted.push(value)}
      onExit={() => false}
    />,
    stdin
  )

  await settle()
  stdin.press('\u0010')
  await settle()
  stdin.press('\u0010')
  await settle()
  stdin.press('\u000E')
  await settle()
  stdin.press('\r')
  await settle()

  assert.deepEqual(submitted, ['second prompt'])
}

async function smokePromptCtrlLClearsScreenAndKeepsDraft(): Promise<void> {
  const stdin = new TestInput()
  const submitted: string[] = []
  let clearCount = 0
  mount(
    <PromptInput
      repoRoot="/tmp"
      history={[]}
      onSubmit={value => submitted.push(value)}
      onExit={() => false}
      onClearScreen={() => clearCount++}
    />,
    stdin
  )

  await settle()
  stdin.press('draft')
  await settle()
  stdin.press('\u000C')
  await settle()
  stdin.press('\r')
  await settle()

  assert.equal(clearCount, 1)
  assert.deepEqual(submitted, ['draft'])
}

async function smokePromptMetaPOpensModelPicker(): Promise<void> {
  const stdin = new TestInput()
  const submitted: string[] = []
  let modelPickerCount = 0
  mount(
    <PromptInput
      repoRoot="/tmp"
      history={[]}
      onSubmit={value => submitted.push(value)}
      onExit={() => false}
      onModelPicker={() => modelPickerCount++}
    />,
    stdin
  )

  await settle()
  stdin.press('\u001Bp')
  await settle()

  assert.equal(modelPickerCount, 1)
  assert.deepEqual(submitted, [])
}

async function smokePromptCtrlCClearsInputWithoutExit(): Promise<void> {
  const stdin = new TestInput()
  const submitted: string[] = []
  let exitCount = 0
  mount(
    <PromptInput
      repoRoot="/tmp"
      history={[]}
      onSubmit={value => submitted.push(value)}
      onExit={() => {
        exitCount++
        return false
      }}
    />,
    stdin
  )

  await settle()
  stdin.press('draft')
  await settle()
  stdin.press('\u0003')
  await settle()
  stdin.press('\r')
  await settle()

  assert.equal(exitCount, 0)
  assert.deepEqual(submitted, [])
}

async function smokePromptEnterRunsSelectedCommandSuggestion(): Promise<void> {
  const stdin = new TestInput()
  const submitted: string[] = []
  mount(
    <PromptInput
      repoRoot="/tmp"
      history={[]}
      onSubmit={value => submitted.push(value)}
      onExit={() => false}
    />,
    stdin
  )

  await settle()
  stdin.press('/mod')
  await settle()
  stdin.press('\r')
  await settle()

  assert.deepEqual(submitted, ['/model'])
}

async function smokePromptLineFeedRunsSelectedCommandSuggestion(): Promise<void> {
  const stdin = new TestInput()
  const submitted: string[] = []
  mount(
    <PromptInput
      repoRoot="/tmp"
      history={[]}
      onSubmit={value => submitted.push(value)}
      onExit={() => false}
    />,
    stdin
  )

  await settle()
  stdin.press('/mod')
  await settle()
  stdin.press('\n')
  await settle()

  assert.deepEqual(submitted, ['/model'])
}

async function smokePromptBufferedTextReturnSubmitsOnce(): Promise<void> {
  const stdin = new TestInput()
  const submitted: string[] = []
  mount(
    <PromptInput
      repoRoot="/tmp"
      history={[]}
      onSubmit={value => submitted.push(value)}
      onExit={() => false}
    />,
    stdin
  )

  await settle()
  stdin.press('/exit\r')
  await settle()

  assert.deepEqual(submitted, ['/exit'])
}

async function smokePromptShiftEnterInsertsNewline(): Promise<void> {
  const stdin = new TestInput()
  const submitted: string[] = []
  mount(
    <PromptInput
      repoRoot="/tmp"
      history={[]}
      onSubmit={value => submitted.push(value)}
      onExit={() => false}
    />,
    stdin
  )

  await settle()
  stdin.press('first')
  stdin.press('\u001B[13;2u')
  stdin.press('second')
  await settle()
  stdin.press('\r')
  await settle()

  assert.deepEqual(submitted, ['first\nsecond'])
}

async function smokePromptEnterSwitchesSelectedModelSuggestion(): Promise<void> {
  const stdin = new TestInput()
  const submitted: string[] = []
  mount(
    <PromptInput
      repoRoot="/tmp"
      history={[]}
      modelProfiles={[
        {name: 'coding', protocol: 'openai', model: 'gpt-5.4', endpoint: 'https://api.example.test', active: true},
        {name: 'local', protocol: 'ollama', model: 'llama', endpoint: 'http://localhost:11434'}
      ]}
      onSubmit={value => submitted.push(value)}
      onExit={() => false}
    />,
    stdin
  )

  await settle()
  stdin.press('/model g')
  await settle()
  stdin.press('\r')
  await settle()

  assert.deepEqual(submitted, ['/model coding'])
}

async function smokePromptCtrlDExitsOnlyOnEmptyInput(): Promise<void> {
  const stdin = new TestInput()
  let exitCount = 0
  mount(
    <PromptInput
      repoRoot="/tmp"
      history={[]}
      onSubmit={() => undefined}
      onExit={() => {
        exitCount++
        return false
      }}
    />,
    stdin
  )

  await settle()
  stdin.press('draft')
  await settle()
  stdin.press('\u0004')
  await settle()
  assert.equal(exitCount, 0)

  stdin.press('\u001B')
  await settle(80)
  stdin.press('\u0004')
  await settle()
  assert.equal(exitCount, 1)
}

async function smokePromptBackspaceDeletesPreviousCharacter(): Promise<void> {
  const stdin = new TestInput()
  const submitted: string[] = []
  mount(
    <PromptInput
      repoRoot="/tmp"
      history={[]}
      onSubmit={value => submitted.push(value)}
      onExit={() => false}
    />,
    stdin
  )

  await settle()
  stdin.press('abc')
  await settle()
  stdin.press('\u007F')
  await settle()
  stdin.press('\r')
  await settle()

  assert.deepEqual(submitted, ['ab'])
}

async function smokePromptBackspaceWorksBeforeReactRerender(): Promise<void> {
  const stdin = new TestInput()
  const submitted: string[] = []
  mount(
    <PromptInput
      repoRoot="/tmp"
      history={[]}
      onSubmit={value => submitted.push(value)}
      onExit={() => false}
    />,
    stdin
  )

  await settle()
  stdin.press('abc')
  stdin.press('\u007F')
  await settle()
  stdin.press('\r')
  await settle()

  assert.deepEqual(submitted, ['ab'])
}

async function smokePromptMetaBackspaceDeletesPreviousWord(): Promise<void> {
  const stdin = new TestInput()
  const submitted: string[] = []
  mount(
    <PromptInput
      repoRoot="/tmp"
      history={[]}
      onSubmit={value => submitted.push(value)}
      onExit={() => false}
    />,
    stdin
  )

  await settle()
  stdin.press('alpha beta')
  await settle()
  stdin.press('\u001B\u007F')
  await settle()
  stdin.press('\r')
  await settle()

  assert.deepEqual(submitted, ['alpha'])
}

async function smokePromptDeleteEscapeSequenceDeletesCharacterUnderCursor(): Promise<void> {
  const stdin = new TestInput()
  const submitted: string[] = []
  mount(
    <PromptInput
      repoRoot="/tmp"
      history={[]}
      onSubmit={value => submitted.push(value)}
      onExit={() => false}
    />,
    stdin
  )

  await settle()
  stdin.press('abc')
  await settle()
  stdin.press('\u001B[D')
  stdin.press('\u001B[3~')
  await settle()
  stdin.press('\r')
  await settle()

  assert.deepEqual(submitted, ['ab'])
}

async function smokePromptMetaDeleteDeletesNextWord(): Promise<void> {
  const stdin = new TestInput()
  const submitted: string[] = []
  mount(
    <PromptInput
      repoRoot="/tmp"
      history={[]}
      onSubmit={value => submitted.push(value)}
      onExit={() => false}
    />,
    stdin
  )

  await settle()
  stdin.press('alpha beta')
  await settle()
  for (let index = 0; index < 4; index++) stdin.press('\u001B[D')
  await settle()
  stdin.press('\u001B[3;3~')
  await settle()
  stdin.press('\r')
  await settle()

  assert.deepEqual(submitted, ['alpha'])
}

async function smokePromptHomeEndMoveCursor(): Promise<void> {
  const stdin = new TestInput()
  const submitted: string[] = []
  mount(
    <PromptInput
      repoRoot="/tmp"
      history={[]}
      onSubmit={value => submitted.push(value)}
      onExit={() => false}
    />,
    stdin
  )

  await settle()
  stdin.press('abc')
  stdin.press('\u001B[H')
  stdin.press('X')
  stdin.press('\u001B[F')
  stdin.press('Y')
  await settle()
  stdin.press('\r')
  await settle()

  assert.deepEqual(submitted, ['XabcY'])
}

async function smokePromptReadlineEditingShortcuts(): Promise<void> {
  const submitted: string[] = []
  const run = async (input: (stdin: TestInput) => void) => {
    const stdin = new TestInput()
    mount(
      <PromptInput
        repoRoot="/tmp"
        history={[]}
        onSubmit={value => submitted.push(value)}
        onExit={() => false}
      />,
      stdin
    )
    await settle()
    input(stdin)
    await settle()
    stdin.press('\r')
    await settle()
  }

  await run(stdin => {
    stdin.press('abc')
    stdin.press('\u0001')
    stdin.press('X')
    stdin.press('\u0005')
    stdin.press('Y')
  })
  await run(stdin => {
    stdin.press('alpha beta')
    stdin.press('\u0017')
  })
  await run(stdin => {
    stdin.press('alpha beta')
    stdin.press('\u0001')
    for (let index = 0; index < 6; index++) stdin.press('\u001B[C')
    stdin.press('\u0015')
  })
  await run(stdin => {
    stdin.press('alpha beta')
    stdin.press('\u0001')
    for (let index = 0; index < 5; index++) stdin.press('\u001B[C')
    stdin.press('\u000B')
  })
  await run(stdin => {
    stdin.press('abc')
    stdin.press('\u0002')
    stdin.press('X')
    stdin.press('\u0006')
    stdin.press('Y')
  })
  await run(stdin => {
    stdin.press('alpha beta')
    stdin.press('\u001Bb')
    stdin.press('X')
  })
  await run(stdin => {
    stdin.press('alpha beta')
    stdin.press('\u0001')
    stdin.press('\u001Bf')
    stdin.press('X')
  })
  await run(stdin => {
    stdin.press('alpha beta')
    stdin.press('\u0001')
    for (let index = 0; index < 6; index++) stdin.press('\u001B[C')
    stdin.press('\u001Bd')
  })

  assert.deepEqual(submitted, ['XabcY', 'alpha', 'beta', 'alpha', 'abXcY', 'alpha Xbeta', 'alphaX beta', 'alpha'])
}

async function smokePromptCtrlDDeletesCharacterUnderCursor(): Promise<void> {
  const stdin = new TestInput()
  const submitted: string[] = []
  mount(
    <PromptInput
      repoRoot="/tmp"
      history={[]}
      onSubmit={value => submitted.push(value)}
      onExit={() => false}
    />,
    stdin
  )

  await settle()
  stdin.press('abc')
  await settle()
  stdin.press('\u001B[D')
  await settle()
  stdin.press('\u0004')
  await settle()
  stdin.press('\r')
  await settle()

  assert.deepEqual(submitted, ['ab'])
}

async function smokePromptChineseBackspaceAndCursorEdit(): Promise<void> {
  const stdin = new TestInput()
  const submitted: string[] = []
  mount(
    <PromptInput
      repoRoot="/tmp"
      history={[]}
      onSubmit={value => submitted.push(value)}
      onExit={() => false}
    />,
    stdin
  )

  await settle()
  stdin.press('你好世界')
  stdin.press('\u001B[D')
  stdin.press('\u007F')
  await settle()
  stdin.press('\r')
  await settle()

  assert.deepEqual(submitted, ['你好界'])
}

async function smokePromptBackspaceDeletesWholeGrapheme(): Promise<void> {
  const stdin = new TestInput()
  const submitted: string[] = []
  mount(
    <PromptInput
      repoRoot="/tmp"
      history={[]}
      onSubmit={value => submitted.push(value)}
      onExit={() => false}
    />,
    stdin
  )

  await settle()
  stdin.press('a👨‍👩‍👧‍👦b')
  stdin.press('\u001B[D')
  stdin.press('\u007F')
  await settle()
  stdin.press('\r')
  await settle()

  assert.deepEqual(submitted, ['ab'])
}

async function smokePromptPastedMultilineEditsAsOneBuffer(): Promise<void> {
  const stdin = new TestInput()
  const submitted: string[] = []
  mount(
    <PromptInput
      repoRoot="/tmp"
      history={[]}
      onSubmit={value => submitted.push(value)}
      onExit={() => false}
    />,
    stdin
  )

  await settle()
  stdin.press('first\nsecond')
  stdin.press('\u001B[D')
  stdin.press('\u007F')
  await settle()
  stdin.press('\r')
  await settle()

  assert.deepEqual(submitted, ['first\nsecod'])
}

async function smokePromptLargePasteUsesReferenceDisplay(): Promise<void> {
  const stdin = new TestInput()
  const stdout = new TestOutput()
  const submitted: string[] = []
  const largePaste = [
    'paste-start',
    ...Array.from({length: 420}, (_, index) => `line-${index + 1}-${'x'.repeat(32)}`),
    'paste-end'
  ].join('\n')
  mount(
    <PromptInput
      repoRoot="/tmp"
      history={[]}
      onSubmit={value => submitted.push(value)}
      onExit={() => false}
    />,
    stdin,
    stdout
  )

  await settle()
  const beforePaste = stdout.content.length
  stdin.press(largePaste)
  await settle()

  const pasteRender = stdout.content.slice(beforePaste)
  assert.match(pasteRender, /\[\.\.\.Pasted text #1 \+[0-9]+ lines\.\.\.\]/)
  assert.equal(pasteRender.includes('line-300'), false, 'large paste should not render the full pasted body into the prompt')

  stdin.press('\r')
  await settle()

  assert.deepEqual(submitted, [largePaste])
}

async function smokePromptBracketedPasteCleansTerminalSequences(): Promise<void> {
  const stdin = new TestInput()
  const stdout = new TestOutput()
  const submitted: string[] = []
  mount(
    <PromptInput
      repoRoot="/tmp"
      history={[]}
      onSubmit={value => submitted.push(value)}
      onExit={() => false}
    />,
    stdin,
    stdout
  )

  await settle()
  const beforePaste = stdout.content.length
  stdin.press('\u001B[200~hello\tworld\r\nnext-\u001B[31mred\u001B[0m\u001B[201~')
  await settle()
  const pastedRender = stdout.content.slice(beforePaste)
  assert.equal(pastedRender.includes('[200~'), false)
  assert.equal(pastedRender.includes('[201~'), false)
  assert.equal(pastedRender.includes('\u001B[31m'), false)
  stdin.press('\r')
  await settle()

  assert.deepEqual(submitted, ['hello    world\nnext-red'])
}

function smokeTextNavigationHelpers(): void {
  assert.equal(previousWordBoundary('alpha beta gamma', 11), 6)
  assert.equal(previousWordBoundary('alpha beta gamma', 6), 0)
  assert.equal(nextWordBoundary('alpha beta gamma', 0), 5)
  assert.equal(nextWordBoundary('alpha beta gamma', 5), 10)
  assert.equal(previousWordBoundary('你好世界', 4), 2)
  assert.equal(previousWordBoundary('你好世界', 2), 0)
  assert.equal(nextWordBoundary('你好世界', 0), 2)
  assert.equal(nextWordBoundary('你好世界', 2), 4)
}

function smokeTextBufferGraphemeHelpers(): void {
  assert.equal(charLength('e\u0301'), 1)
  assert.equal(charLength('👨‍👩‍👧‍👦'), 1)
  assert.equal(displayWidth('你好'), 4)
  assert.equal(padDisplayEnd('你', 4), '你  ')
  assert.equal(isBackspaceInput('', {delete: true}, '\u007F'), true)
  assert.equal(isDeleteInput('', {delete: true}, '\u007F'), false)
  assert.equal(isBackspaceInput('', {delete: true}, '\u001B[3~'), false)
  assert.equal(isDeleteInput('', {delete: true}, '\u001B[3~'), true)
}

function smokeModelProfileCompletion(): void {
  assert.equal(isModelProfileQuery('/model gpt'), true)
  assert.equal(isModelProfileQuery('/status'), false)
  const matches = modelProfileMatches('/model gpt', [
    {name: 'coding', protocol: 'openai', model: 'gpt-5.4', endpoint: 'https://api.example.test', active: true},
    {name: 'local', protocol: 'ollama', model: 'llama', endpoint: 'http://localhost:11434'}
  ])
  assert.equal(matches.length, 1)
  assert.equal(matches[0]?.insertText, '/model coding')
  assert.equal(matches[0]?.active, true)
}

function mount(node: React.ReactNode, stdin: TestInput, stdout = new TestOutput()): Instance {
  const instance = render(node, {
    stdin,
    stdout,
    stderr: new TestOutput(),
    exitOnCtrlC: false,
    patchConsole: false
  } as unknown as RenderOptions)
  mounted.push(instance)
  return instance
}

function options(): Array<SelectOption<string>> {
  return [
    {value: 'alpha', label: 'Alpha', description: 'first'},
    {value: 'beta', label: 'Beta', description: 'second'},
    {value: 'gamma', label: 'Gamma', description: 'third'}
  ]
}

function manyOptions(count: number): Array<SelectOption<string>> {
  return Array.from({length: count}, (_, index) => ({
    value: `item-${index + 1}`,
    label: `Item ${index + 1}`
  }))
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

try {
  console.warn = (...args: unknown[]) => consoleMessages.push(args.map(String).join(' '))
  console.error = (...args: unknown[]) => consoleMessages.push(args.map(String).join(' '))
  await smokeSelectArrowNavigation()
  await smokeSelectLineFeedSubmits()
  await smokeSelectFilter()
  await smokeSelectFilterDeleteKeyEditsQuery()
  await smokeSelectFilterDeleteEscapeSequenceEditsQuery()
  await smokeSelectEscapeBehavior()
  await smokeEmptySelectCanCancel()
  await smokeSelectClampsSelectionAfterOptionsShrink()
  await smokeSelectPageNavigation()
  await smokeSelectCtrlPNavigation()
  await smokePermissionShortcutsSelectDecision()
  await smokeModelPickerNavigation()
  await smokePromptEscapeCancelsOnlyWhenInputIsEmpty()
  await smokePromptNativeCursorAnchorsInsideTextbox()
  await smokePromptNativeCursorWrapsInsideTextbox()
  await smokePromptHistorySearchTabAcceptsMatch()
  await smokePromptHistorySearchEnterExecutesMatch()
  await smokePromptHistorySearchCtrlRCyclesMatches()
  await smokePromptHistorySearchCtrlCCancelsSearch()
  await smokePromptCtrlPNNavigateHistory()
  await smokePromptCtrlLClearsScreenAndKeepsDraft()
  await smokePromptMetaPOpensModelPicker()
  await smokePromptCtrlCClearsInputWithoutExit()
  await smokePromptEnterRunsSelectedCommandSuggestion()
  await smokePromptLineFeedRunsSelectedCommandSuggestion()
  await smokePromptBufferedTextReturnSubmitsOnce()
  await smokePromptShiftEnterInsertsNewline()
  await smokePromptEnterSwitchesSelectedModelSuggestion()
  await smokePromptCtrlDExitsOnlyOnEmptyInput()
  await smokePromptBackspaceDeletesPreviousCharacter()
  await smokePromptBackspaceWorksBeforeReactRerender()
  await smokePromptMetaBackspaceDeletesPreviousWord()
  await smokePromptDeleteEscapeSequenceDeletesCharacterUnderCursor()
  await smokePromptMetaDeleteDeletesNextWord()
  await smokePromptHomeEndMoveCursor()
  await smokePromptReadlineEditingShortcuts()
  await smokePromptCtrlDDeletesCharacterUnderCursor()
  await smokePromptChineseBackspaceAndCursorEdit()
  await smokePromptBackspaceDeletesWholeGrapheme()
  await smokePromptPastedMultilineEditsAsOneBuffer()
  await smokePromptLargePasteUsesReferenceDisplay()
  await smokePromptBracketedPasteCleansTerminalSequences()
  smokeSafeInputTerminalSequences()
  smokeTextNavigationHelpers()
  smokeTextBufferGraphemeHelpers()
  smokeModelProfileCompletion()
  assert.deepEqual(consoleMessages, [])
  console.log('terminal interaction smoke passed')
} finally {
  console.warn = originalWarn
  console.error = originalError
  for (const instance of mounted.splice(0)) {
    instance.unmount()
    instance.cleanup()
  }
}
