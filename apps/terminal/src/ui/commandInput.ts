export type InputCommandKind =
  | 'exit'
  | 'help'
  | 'model_picker'
  | 'model_switch'
  | 'resume_picker'
  | 'fold'
  | 'unfold'
  | 'queue'
  | 'cancel'
  | 'clear'
  | 'slash'
  | 'message'

export function isExitCommand(value: string): boolean {
  return value.trim() === '/exit'
}

export function classifyInputCommand(value: string): InputCommandKind {
  if (isExitCommand(value)) return 'exit'
  if (value === '/help' || value === '?') return 'help'
  if (value === '/model' || value === '/models') return 'model_picker'
  if (/^\/models?\s+\S/.test(value)) return 'model_switch'
  if (value === '/resume') return 'resume_picker'
  if (value === '/fold') return 'fold'
  if (value === '/unfold') return 'unfold'
  if (value === '/queue') return 'queue'
  if (value === '/cancel') return 'cancel'
  if (value === '/clear') return 'clear'
  if (value.startsWith('/')) return 'slash'
  return 'message'
}
