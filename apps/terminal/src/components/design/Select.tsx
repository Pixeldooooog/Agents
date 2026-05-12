import React, {useEffect, useMemo, useState} from 'react'
import {Box, Text, useStdin} from 'ink'
import figures from 'figures'
import {colors} from '../../ui/theme.js'
import {dropLastChar, isBackspaceInput, isDeleteInput} from '../../ui/textBuffer.js'
import {useSafeInput} from '../../hooks/useSafeInput.js'

export type SelectOption<T extends string = string> = {
  value: T
  label: string
  description?: string
  meta?: string
  shortcut?: string
  hideShortcut?: boolean
  disabled?: boolean
  active?: boolean
}

export function Select<T extends string>({
  options,
  initialValue,
  onSelect,
  onCancel,
  active = true,
  filterable = false,
  emptyLabel = 'No options available',
  maxVisible
}: {
  options: Array<SelectOption<T>>
  initialValue?: T
  onSelect: (value: T) => void
  onCancel?: () => void
  active?: boolean
  filterable?: boolean
  emptyLabel?: string
  maxVisible?: number
}) {
  const [query, setQuery] = useState('')
  const filteredOptions = useMemo(() => {
    if (!filterable || !query.trim()) return options
    const needle = query.trim().toLowerCase()
    return options.filter(option => [option.label, option.meta, option.description].filter(Boolean).join(' ').toLowerCase().includes(needle))
  }, [filterable, options, query])
  const enabledOptions = useMemo(() => filteredOptions.filter(option => !option.disabled), [filteredOptions])
  const initialIndex = Math.max(0, enabledOptions.findIndex(option => option.value === initialValue || option.active))
  const [selected, setSelected] = useState(initialIndex)
  const {isRawModeSupported} = useStdin()
  const selectedOption = enabledOptions[Math.min(selected, Math.max(0, enabledOptions.length - 1))]
  const window = visibleOptionWindow(filteredOptions, selectedOption, maxVisible)

  useEffect(() => {
    setSelected(current => Math.min(current, Math.max(0, enabledOptions.length - 1)))
  }, [enabledOptions.length])

  useSafeInput((input, key) => {
    const returnKey = key.return || input === '\r' || input === '\n'
    const shortcut = enabledOptions.find(option => option.shortcut === input)
    if (shortcut) {
      onSelect(shortcut.value)
      return
    }
    if (filterable && (isBackspaceInput(input, key) || isDeleteInput(input, key))) {
      setQuery(dropLastChar)
      setSelected(0)
      return
    }
    if (!enabledOptions.length) {
      if (key.escape || (key.ctrl && input === 'c')) onCancel?.()
      return
    }
    if (key.escape || (key.ctrl && input === 'c')) {
      if (filterable && query) {
        setQuery('')
        setSelected(0)
        return
      }
      onCancel?.()
      return
    }
    if (filterable && input && !key.ctrl && !key.meta && !returnKey) {
      setQuery(current => current + input)
      setSelected(0)
      return
    }
    if (key.upArrow) {
      setSelected(current => (current - 1 + enabledOptions.length) % enabledOptions.length)
      return
    }
    if (key.downArrow) {
      setSelected(current => (current + 1) % enabledOptions.length)
      return
    }
    if (key.ctrl && input === 'p') {
      setSelected(current => (current - 1 + enabledOptions.length) % enabledOptions.length)
      return
    }
    if (key.ctrl && input === 'n') {
      setSelected(current => (current + 1) % enabledOptions.length)
      return
    }
    if (key.pageUp) {
      setSelected(current => Math.max(0, current - selectPageSize(enabledOptions.length, maxVisible)))
      return
    }
    if (key.pageDown) {
      setSelected(current => Math.min(Math.max(0, enabledOptions.length - 1), current + selectPageSize(enabledOptions.length, maxVisible)))
      return
    }
    if (returnKey && selectedOption) onSelect(selectedOption.value)
  }, {isActive: Boolean(active && isRawModeSupported)})

  if (!options.length) return <Text dimColor>{emptyLabel}</Text>

  return (
    <Box flexDirection="column">
      {filterable ? (
        <Box marginBottom={1}>
          <Text dimColor>filter: </Text>
          <Text>{query || ' '}</Text>
        </Box>
      ) : null}
      {window.hiddenBefore ? <Text dimColor>↑ {window.hiddenBefore} more</Text> : null}
      {window.options.map(option => {
        const index = enabledOptions.findIndex(enabled => enabled.value === option.value)
        const selectedRow = index === selected && !option.disabled
        return (
          <Box key={option.value} flexDirection="column">
            <Box>
              <Text color={selectedRow ? colors.cyan : option.disabled ? colors.dim : colors.text}>
                {selectedRow ? figures.pointer : ' '} {option.active ? '●' : ' '} {option.label}
              </Text>
              {option.shortcut && !option.hideShortcut ? <Text dimColor>  {option.shortcut}</Text> : null}
              {option.meta ? <Text dimColor>  {option.meta}</Text> : null}
            </Box>
            {option.description ? (
              <Box paddingLeft={4}>
                <Text dimColor>{option.description}</Text>
              </Box>
            ) : null}
          </Box>
        )
      })}
      {window.hiddenAfter ? <Text dimColor>↓ {window.hiddenAfter} more</Text> : null}
      {!filteredOptions.length ? <Text dimColor>No matching options</Text> : null}
    </Box>
  )
}

function selectPageSize(optionCount: number, maxVisible: number | undefined): number {
  return Math.max(1, Math.min(optionCount || 1, maxVisible ?? 6))
}

function visibleOptionWindow<T extends string>(
  options: Array<SelectOption<T>>,
  selectedOption: SelectOption<T> | undefined,
  maxVisible: number | undefined
): {options: Array<SelectOption<T>>; hiddenBefore: number; hiddenAfter: number} {
  if (!maxVisible || options.length <= maxVisible) return {options, hiddenBefore: 0, hiddenAfter: 0}
  const selectedIndex = Math.max(0, selectedOption ? options.findIndex(option => option.value === selectedOption.value) : 0)
  const visibleCount = Math.max(1, maxVisible)
  const start = Math.max(0, Math.min(selectedIndex - Math.floor(visibleCount / 2), options.length - visibleCount))
  const end = Math.min(options.length, start + visibleCount)
  return {
    options: options.slice(start, end),
    hiddenBefore: start,
    hiddenAfter: options.length - end
  }
}
