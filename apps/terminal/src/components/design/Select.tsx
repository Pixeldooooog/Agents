import React, {useEffect, useMemo, useState} from 'react'
import {Box, Text} from 'ink'
import figures from 'figures'
import {colors} from '../../ui/theme.js'
import {
  enabledSelectOptions,
  filterSelectOptions,
  initialSelectIndex,
  visibleOptionWindow,
  type SelectOption
} from './selectOptions.js'
import {useSelectKeyboard} from './useSelectKeyboard.js'

export type {SelectOption} from './selectOptions.js'

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
  const filteredOptions = useMemo(() => filterSelectOptions(options, filterable, query), [filterable, options, query])
  const enabledOptions = useMemo(() => enabledSelectOptions(filteredOptions), [filteredOptions])
  const initialIndex = initialSelectIndex(enabledOptions, initialValue)
  const [selected, setSelected] = useState(initialIndex)
  const selectedOption = enabledOptions[Math.min(selected, Math.max(0, enabledOptions.length - 1))]
  const window = visibleOptionWindow(filteredOptions, selectedOption, maxVisible)

  useEffect(() => {
    setSelected(current => Math.min(current, Math.max(0, enabledOptions.length - 1)))
  }, [enabledOptions.length])

  useSelectKeyboard({
    active,
    enabledOptions,
    filterable,
    maxVisible,
    onCancel,
    onSelect,
    query,
    selectedOption,
    setQuery,
    setSelected
  })

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
