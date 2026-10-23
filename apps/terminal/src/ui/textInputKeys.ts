export function isBackspaceInput(input: string, key: {backspace?: boolean; delete?: boolean}, rawInput = ''): boolean {
  if (key.backspace || input === '\u007F' || input === '\b') return true
  if (key.delete && rawInput && !isDeleteSequence(rawInput)) return true
  return Boolean(key.delete && !rawInput)
}

export function isDeleteInput(input: string, key: {delete?: boolean}, rawInput = ''): boolean {
  return Boolean(isDeleteSequence(rawInput) || input === '\u001B[3~' || (key.delete && isDeleteSequence(rawInput)))
}

function isDeleteSequence(value: string): boolean {
  return value === '\u001B[3~' || /^\u001B\[3[;:].*[~u]$/.test(value)
}
