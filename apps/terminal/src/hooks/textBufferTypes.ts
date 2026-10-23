import type {ModelProfile} from "../protocol/terminalHostProtocol.js"
import type {CommandDef} from "../ui/commands.js"

export type TextBufferOptions = {
  disabled?: boolean
  repoRoot: string
  commands?: CommandDef[]
  modelProfiles?: ModelProfile[]
  history?: string[]
  onSubmit: (value: string, displayValue?: string) => void
  onExit: () => void | boolean
  onCancel?: () => void | boolean
  onClearScreen?: () => void
  onModelPicker?: () => void
}

export type TextBufferKey = {
  return?: boolean
  escape?: boolean
  backspace?: boolean
  delete?: boolean
  mouse?: boolean
  wheelUp?: boolean
  wheelDown?: boolean
  upArrow?: boolean
  downArrow?: boolean
  leftArrow?: boolean
  rightArrow?: boolean
  ctrl?: boolean
  meta?: boolean
  shift?: boolean
  tab?: boolean
  home?: boolean
  end?: boolean
  pageUp?: boolean
  pageDown?: boolean
}
