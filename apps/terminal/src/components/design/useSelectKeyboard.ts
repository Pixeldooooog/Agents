import type {Dispatch, SetStateAction} from 'react'
import {useStdin} from 'ink'
import {dropLastChar, isBackspaceInput, isDeleteInput} from '../../ui/textBuffer.js'
import {useSafeInput} from '../../hooks/useSafeInput.js'
import type {SelectOption} from './selectOptions.js'
import {selectPageSize} from './selectOptions.js'

type SelectKeyboardOptions<T extends string> = {
  active: boolean
  enabledOptions: Array<SelectOption<T>>
  filterable: boolean
  maxVisible?: number
  onCancel?: () => void
  onSelect: (value: T) => void
  query: string
  selectedOption?: SelectOption<T>
  setQuery: Dispatch<SetStateAction<string>>
  setSelected: Dispatch<SetStateAction<number>>
}

export function useSelectKeyboard<T extends string>(options: SelectKeyboardOptions<T>) {
  const {isRawModeSupported} = useStdin()
  useSafeInput((input, key) => {
    const returnKey = key.return || input === '\r' || input === '\n'
    const shortcut = options.enabledOptions.find(option => option.shortcut === input)
    if (shortcut) {
      options.onSelect(shortcut.value)
      return
    }
    if (options.filterable && (isBackspaceInput(input, key) || isDeleteInput(input, key))) {
      options.setQuery(dropLastChar)
      options.setSelected(0)
      return
    }
    if (!options.enabledOptions.length) {
      if (key.escape || (key.ctrl && input === 'c')) options.onCancel?.()
      return
    }
    if (key.escape || (key.ctrl && input === 'c')) {
      if (options.filterable && options.query) {
        options.setQuery('')
        options.setSelected(0)
        return
      }
      options.onCancel?.()
      return
    }
    if (options.filterable && input && !key.ctrl && !key.meta && !returnKey) {
      options.setQuery(current => current + input)
      options.setSelected(0)
      return
    }
    if (key.upArrow || (key.ctrl && input === 'p')) {
      options.setSelected(current => (current - 1 + options.enabledOptions.length) % options.enabledOptions.length)
      return
    }
    if (key.downArrow || (key.ctrl && input === 'n')) {
      options.setSelected(current => (current + 1) % options.enabledOptions.length)
      return
    }
    if (key.pageUp) {
      options.setSelected(current => Math.max(0, current - selectPageSize(options.enabledOptions.length, options.maxVisible)))
      return
    }
    if (key.pageDown) {
      options.setSelected(current => Math.min(Math.max(0, options.enabledOptions.length - 1), current + selectPageSize(options.enabledOptions.length, options.maxVisible)))
      return
    }
    if (returnKey && options.selectedOption) options.onSelect(options.selectedOption.value)
  }, {isActive: Boolean(options.active && isRawModeSupported)})
}
