import assert from 'node:assert/strict'
import React from 'react'
import {renderToString} from 'ink'
import {WELCOME_ROWS, isFullscreenLayoutEnabled} from '../src/app/terminalLayout.js'
import {ApprovalPrompt} from '../src/components/ApprovalPrompt.js'
import {LiveTurn} from '../src/components/LiveTurn.js'
import {MessageViewport} from '../src/components/MessageViewport.js'
import {estimateTranscriptLines} from '../src/components/messageViewportLayout.js'
import {MessageList} from '../src/components/MessageList.js'
import {ModelPicker} from '../src/components/ModelPicker.js'
import {PromptInput, PromptInputOverlay, estimatePromptRows} from '../src/components/PromptInput.js'
import {PromptFooter} from '../src/components/prompt/PromptFooter.js'
import {PromptLine} from '../src/components/prompt/PromptLine.js'
import {cursorPositionFor} from '../src/components/prompt/promptCursor.js'
import {SessionPicker} from '../src/components/SessionPicker.js'
import {Welcome} from '../src/components/Welcome.js'
import type {TranscriptItem} from '../src/components/MessageList.js'
import type {ModelProfile, PendingApproval, SessionRecord} from '../src/protocol/terminalHostProtocol.js'
import {classifyInputCommand, commandHelpRows, commandMatches, isCommandAvailableWhileBusy, isExitCommand, terminalCommands} from '../src/ui/commands.js'
import {sessionTableRows} from '../src/ui/sessionRows.js'
import {transcriptFromSession} from '../src/ui/sessionTranscript.js'
import {nextScrollOffset} from '../src/ui/scroll.js'

const runtime = {
  protocol: 'openai-responses',
  model: 'gpt-5.4',
  model_profile: 'coding'
}

const workspace = {
  path: '/tmp/agents',
  display: '~/program/Agents',
  tenant_id: 'local',
  user_id: 'user',
  agent_id: 'agent',
  workspace_id: 'workspace'
}

const profiles: ModelProfile[] = [
  {name: 'coding', protocol: 'openai-responses', model: 'gpt-5.4', endpoint: 'api.openai.test', configured: true, active: true},
  {name: 'fallback', protocol: 'scripted', model: 'echo', configured: false}
]

delete process.env.AGENTS_TERMINAL_FULLSCREEN
assert.equal(isFullscreenLayoutEnabled(), false)
process.env.AGENTS_TERMINAL_FULLSCREEN = '1'
assert.equal(isFullscreenLayoutEnabled(), true)
process.env.AGENTS_TERMINAL_FULLSCREEN = '0'
assert.equal(isFullscreenLayoutEnabled(), false)
delete process.env.AGENTS_TERMINAL_FULLSCREEN

const sessions: SessionRecord[] = [
  {id: 'session_1234567890abcdef', short_id: '1234567890abcdef', updated: '2026-05-07 10:00', model: 'openai-responses · gpt-5.4', messages: '8', workspace: '~/program/Agents'}
]

const approval: PendingApproval = {
  runId: 'run-1',
  approvalId: 'call-1',
  toolName: 'filesystem.write',
  args: {path: 'out.txt', content: 'hello'},
  risk: 'medium',
  reason: 'writes a file in the workspace'
}

const transcript: TranscriptItem[] = [
  {kind: 'user', text: 'hello'},
  {kind: 'assistant', text: 'ready'},
  {kind: 'status', label: 'done', text: '1s'},
  {kind: 'table', title: 'Status', rows: [['model', 'gpt-5.4']]},
  {kind: 'models', profiles}
]

assertContains(
  'Welcome',
  renderClean(<Welcome runtime={runtime} workspace={workspace} profile="coding" permission="guarded" sandbox="local" toolCount={6} />),
  ['Agents Code', 'gpt-5.4', '~/program/Agents', '/model']
)
assert.equal(renderClean(<Welcome runtime={runtime} workspace={workspace} profile="coding" permission="guarded" sandbox="local" toolCount={6} />).split('\n').length, WELCOME_ROWS)

assertContains(
  'ApprovalPrompt',
  renderClean(<ApprovalPrompt approval={approval} onDecision={() => undefined} />),
  ['Permission Request', 'filesystem.write', 'medium', 'Allow once', 'Allow for run', 'Deny', 'enter', 'confirm', 'esc']
)

assertContains(
  'PromptLine',
  renderClean(<PromptLine value="你好" before="你" current="好" after="" placeholder="ask or type / for commands" />),
  ['┏', '❯', '你好']
)
assertContains(
  'PromptLine cursor split',
  renderClean(<PromptLine value="abc" cursor={1} before="" current="" after="" placeholder="ask or type / for commands" />),
  ['abc']
)
assert.doesNotMatch(
  renderToString(<PromptLine value="abc" cursor={1} before="" current="" after="" placeholder="ask or type / for commands" />, {columns: 100}),
  /\x1B\[7m/,
  'PromptLine should rely on the native terminal cursor instead of drawing a block cursor'
)

const promptInputLines = renderClean(<PromptInput repoRoot="/tmp" history={[]} onSubmit={() => undefined} onExit={() => false} />).trimEnd().split('\n')
assert.match(promptInputLines[0] ?? '', /─/, 'PromptInput should render a divider above the textbox')
assert.match(promptInputLines[promptInputLines.length - 1] ?? '', /cmd/, 'PromptInput should render shortcut hints below the textbox')
assert.match(promptInputLines[promptInputLines.length - 1] ?? '', /terminal/, 'PromptInput should describe default scroll as terminal scroll')
assert.match(promptInputLines[promptInputLines.length - 1] ?? '', /line/, 'PromptInput should advertise multiline input on wide terminals')
assert.match(promptInputLines[promptInputLines.length - 1] ?? '', /clear/, 'PromptInput should advertise local screen clearing on wide terminals')
const narrowPromptInputLines = stripAnsi(renderToString(<PromptInput repoRoot="/tmp" history={[]} onSubmit={() => undefined} onExit={() => false} />, {columns: 24})).trimEnd().split('\n')
assert.equal(narrowPromptInputLines.filter(line => /^─+$/.test(line)).length, 0, 'PromptInput divider should not wrap into extra full-width lines on narrow terminals')
assert.equal(narrowPromptInputLines.filter(line => /^─+/.test(line)).length, 1, 'PromptInput should keep a single divider row on narrow terminals')
assert.doesNotMatch(narrowPromptInputLines[narrowPromptInputLines.length - 1] ?? '', /line/, 'PromptInput should keep shortcut hints compact on narrow terminals')
assert.equal(estimatePromptRows('', 100), 5)
assert.equal(estimatePromptRows('', 24, 'ask or type / for commands'), narrowPromptInputLines.length)
assert.equal(estimatePromptRows('first\nsecond', 100), 6)
assert.equal(estimatePromptRows('/exit\n\n', 100), 7)
assert.ok(
  estimatePromptRows('/permissions', 24, '', '[sources|audit|guarded|auto|ask|deny|allow <tool>|deny <tool>|ask <tool>|remove <tool>]') > estimatePromptRows('/permissions', 24),
  'PromptInput row estimate should reserve space for wrapped command argument hints on narrow terminals'
)
const promptPanel = renderClean(<PromptFooter mode="panel" suggestions={[{name: '/model', description: 'switch model', kind: 'command'}]} selected={0} />)
assert.match(promptPanel, /Commands/, 'PromptFooter panel mode should render suggestions separately from the hint row')
const promptOverlay = renderClean(<PromptInputOverlay overlay={{suggestions: [{name: '/model', description: 'switch model', kind: 'command'}], selected: 0}} rows={5} />)
assert.match(promptOverlay, /Commands/, 'PromptInputOverlay should render suggestions in a bounded fullscreen overlay slot')
assert.doesNotMatch(promptOverlay, /ask or type/, 'PromptInputOverlay should not render prompt chrome inside the overlay')
const promptHint = renderClean(<PromptFooter mode="hint" suggestions={[{name: '/model', description: 'switch model', kind: 'command'}]} selected={0} />)
assert.doesNotMatch(promptHint, /switch model/, 'PromptFooter hint mode should not render suggestions below the input')
assert.match(renderClean(<PromptFooter mode="hint" suggestions={[]} selected={0} fullscreen />), /pgup\/dn/, 'PromptFooter fullscreen hint should show app-level page scroll keys')
const clippedPanel = renderClean(<PromptFooter mode="panel" suggestions={[
  {name: '/one', description: 'first command', kind: 'command'},
  {name: '/two', description: 'second command', kind: 'command'},
  {name: '/three', description: 'third command', kind: 'command'}
]} selected={0} maxSuggestions={2} />)
assert.match(clippedPanel, /first command/, 'PromptFooter fixed panel should show visible suggestions')
assert.match(clippedPanel, /second command/, 'PromptFooter fixed panel should show the requested number of suggestions')
assert.doesNotMatch(clippedPanel, /third command/, 'PromptFooter fixed panel should clip extra suggestions instead of growing into the prompt')
assert.deepEqual(cursorPositionFor('你好世界', 2, 80), {line: 0, column: 4})
assert.deepEqual(cursorPositionFor('abcdef', 4, 4), {line: 1, column: 1})
assert.deepEqual(cursorPositionFor('first\nsecond', 8, 80), {line: 1, column: 2})

assertContains(
  'ModelPicker',
  renderClean(<ModelPicker profiles={profiles} onSelect={() => undefined} onCancel={() => undefined} />),
  ['Model Profiles', 'coding', 'openai-responses', 'gpt-5.4']
)
const modelPickerOutput = renderClean(<ModelPicker profiles={profiles} onSelect={() => undefined} onCancel={() => undefined} />)
assert.doesNotMatch(modelPickerOutput, /filter:/, 'ModelPicker should stay a compact arrow-driven card without a filter prompt')
assert.doesNotMatch(modelPickerOutput, /api\.openai\.test/, 'ModelPicker should not render endpoint detail rows by default')
const manyProfiles = Array.from({length: 12}, (_, index) => ({
  name: `profile-${index + 1}`,
  protocol: 'openai-responses',
  model: `model-${index + 1}`,
  configured: true,
  active: index === 0
}))
const clippedModels = renderClean(<ModelPicker profiles={manyProfiles} onSelect={() => undefined} onCancel={() => undefined} />)
assert.match(clippedModels, /and 2 more/, 'ModelPicker should clip long profile lists instead of growing past the dialog')
assert.doesNotMatch(clippedModels, /profile-12/, 'ModelPicker should keep off-window options hidden until navigated')

assertContains(
  'SessionPicker',
  renderClean(<SessionPicker sessions={sessions} onSelect={() => undefined} onCancel={() => undefined} />),
  ['Resume Session', '1234567890abcdef', '8 messages', 'gpt-5.4']
)

assertContains(
  'LiveTurn',
  renderClean(<LiveTurn assistant="final answer" reasoning="checking" label="openai-responses · gpt-5.4" collapsed={false} />),
  ['Assistant Reply', 'final answer', 'Thinking', 'checking']
)

const longLiveReply = renderClean(<LiveTurn assistant={Array.from({length: 20}, (_, index) => `live-reply-${index + 1}`).join('\n')} reasoning="" label="openai-responses · gpt-5.4" collapsed={true} />)
assert.match(longLiveReply, /live-reply-20/, 'LiveTurn assistant replies should stay expanded by default')
assert.doesNotMatch(longLiveReply, /blocks hidden/, 'LiveTurn assistant replies should not require ctrl+o by default')

const livePreview = renderClean(<LiveTurn assistant={Array.from({length: 8}, (_, index) => `live-line-${index + 1}`).join('\n')} reasoning="" label="openai-responses · gpt-5.4" collapsed={false} maxLines={2} />)
assert.match(livePreview, /blocks hidden/, 'LiveTurn preview should crop long live output in fixed fullscreen chrome')

assertContains(
  'MessageList',
  renderClean(<MessageList items={transcript} collapsed={false} />),
  ['hello', 'ready', 'done', 'Status', 'coding']
)

assertContains(
  'MessageList assistant unfolded',
  renderClean(<MessageList items={[{kind: 'assistant', text: Array.from({length: 20}, (_, index) => `reply-line-${index + 1}`).join('\n')}]} collapsed={true} />),
  ['Assistant Reply', 'reply-line-20', '----------------']
)
assert.doesNotMatch(
  renderClean(<MessageList items={[{kind: 'assistant', text: 'live reply', live: true}]} collapsed={true} />),
  /----------------/,
  'MessageList should not draw the final divider while assistant output is still live'
)
const viewportLongAssistant = renderClean(<MessageViewport items={[{kind: 'assistant', text: Array.from({length: 20}, (_, index) => `reply-line-${index + 1}`).join('\n')}]} collapsed={true} height={6} scrollOffset={0} />)
assert.match(viewportLongAssistant, /reply-line-20/, 'MessageViewport should not fold the final assistant reply')
assert.doesNotMatch(viewportLongAssistant, /blocks hidden/, 'MessageViewport should not show fold markers for final assistant replies')
const scrolledLongAssistant = renderClean(<MessageViewport items={[{kind: 'assistant', text: Array.from({length: 20}, (_, index) => `reply-line-${index + 1}`).join('\n')}]} collapsed={true} height={6} scrollOffset={5} />)
assert.match(scrolledLongAssistant, /lines above latest/, 'MessageViewport should show scroll position while paging within a long assistant reply')
assert.match(scrolledLongAssistant, /reply-line-15/, 'MessageViewport should page inside a long assistant reply instead of pinning the last line')
assert.doesNotMatch(scrolledLongAssistant, /reply-line-20/, 'MessageViewport should not force the latest line while scrolled inside a long assistant reply')
assert.equal(
  estimateTranscriptLines([{kind: 'assistant', text: 'x'.repeat(60)}], true, undefined, 20),
  9,
  'MessageViewport should count terminal soft-wrap rows when calculating scroll limits'
)
assert.equal(
  nextScrollOffset({current: 4, previousLines: 20, nextLines: 27, max: 30}),
  11,
  'scroll offset should grow with streamed output while the user is reading history'
)
assert.equal(
  nextScrollOffset({current: 0, previousLines: 20, nextLines: 27, max: 30}),
  0,
  'scroll offset should stay pinned to latest when the user has not scrolled up'
)
assert.equal(
  nextScrollOffset({current: 8, previousLines: 27, nextLines: 20, max: 6}),
  6,
  'scroll offset should clamp after shrink or resize'
)

assertContains(
  'MessageViewport bottom follows latest',
  renderClean(<MessageViewport items={Array.from({length: 12}, (_, index) => ({kind: 'status' as const, label: `status-${index + 1}`}))} collapsed={true} height={4} scrollOffset={0} />),
  ['earlier messages hidden', 'status-12']
)
const scrolledViewport = renderClean(<MessageViewport items={Array.from({length: 12}, (_, index) => ({kind: 'status' as const, label: `status-${index + 1}`}))} collapsed={true} height={5} scrollOffset={4} />)
assert.match(scrolledViewport, /lines above latest/, 'MessageViewport should show when the user is scrolled above the latest output')
assert.doesNotMatch(scrolledViewport, /status-12/, 'MessageViewport should not force latest output while the user is scrolled up')
const scrolledLiveViewport = renderClean(<MessageViewport items={[{kind: 'assistant', text: 'older reply'}, {kind: 'assistant', text: 'live reply', live: true}]} collapsed={true} height={3} scrollOffset={1} />)
assert.match(scrolledLiveViewport, /new output below/, 'MessageViewport should show a live-output hint while the user is scrolled above an active stream')
const scrolledFinishedViewport = renderClean(<MessageViewport items={[{kind: 'assistant', text: 'older reply'}, {kind: 'assistant', text: 'finished reply'}]} collapsed={true} height={3} scrollOffset={1} />)
assert.doesNotMatch(scrolledFinishedViewport, /new output below/, 'MessageViewport should clear the live-output hint after the stream finishes')

assert.equal(isCommandAvailableWhileBusy('/cancel'), true)
assert.equal(isCommandAvailableWhileBusy('/cancel now'), false)
assert.equal(isCommandAvailableWhileBusy('/queue'), true)
assert.equal(isCommandAvailableWhileBusy('/exit'), true)
assert.equal(isCommandAvailableWhileBusy('/exit now'), false)
assert.equal(isCommandAvailableWhileBusy('/clear'), false)
assert.equal(isCommandAvailableWhileBusy('/model coding'), false)
assert.equal(isExitCommand('/exit'), true)
assert.equal(isExitCommand('/exit now'), false)
assert.equal(classifyInputCommand('/exit'), 'exit')
assert.equal(classifyInputCommand('/help'), 'help')
assert.equal(classifyInputCommand('?'), 'help')
assert.equal(classifyInputCommand('/model'), 'model_picker')
assert.equal(classifyInputCommand('/model coding'), 'model_switch')
assert.equal(classifyInputCommand('/resume'), 'resume_picker')
assert.equal(classifyInputCommand('/resume latest'), 'slash')
assert.equal(classifyInputCommand('hello'), 'message')
assert.deepEqual(commandHelpRows([{name: '/status', description: 'session state'}]), [['/status', 'session state · idle']])
assert.deepEqual(commandHelpRows([{name: '/exit', description: 'leave', local: true, availability: 'always'}]), [['/exit', 'leave · local']])
const dynamicCommands = terminalCommands([{name: '/memory', description: 'manage memories', argumentHint: '<action>', source: 'skill'}])
assert.equal(dynamicCommands.some(command => command.name === '/memory'), true)
assert.equal(commandMatches('/mem', dynamicCommands)[0]?.name, '/memory')
assert.deepEqual(commandHelpRows(dynamicCommands).find(row => row[0] === '/memory'), ['/memory', 'manage memories · <action> · skill · idle'])
assert.deepEqual(sessionTableRows([]), [['sessions', 'none']])
assert.deepEqual(sessionTableRows(sessions), [['1234567890abcdef', '2026-05-07 10:00 · 8 messages · openai-responses · gpt-5.4 · ~/program/Agents']])
assert.deepEqual(transcriptFromSession([{role: 'user', content: 'hi'}, {role: 'assistant', content: 'ok'}]), [
  {kind: 'user', text: 'hi'},
  {kind: 'assistant', text: 'ok'}
])

console.log('terminal render smoke passed')

function renderClean(node: React.ReactNode): string {
  return stripAnsi(renderToString(node, {columns: 100}))
}

function assertContains(name: string, output: string, expected: string[]): void {
  assert.notEqual(output.trim(), '', `${name} rendered blank output`)
  for (const value of expected) {
    assert.match(output, new RegExp(escapeRegExp(value)), `${name} did not render ${value}`)
  }
}

function stripAnsi(value: string): string {
  return value.replace(/\x1B\[[0-?]*[ -/]*[@-~]/g, '')
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}
