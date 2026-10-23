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

export function filterSelectOptions<T extends string>(
  options: Array<SelectOption<T>>,
  filterable: boolean,
  query: string
): Array<SelectOption<T>> {
  if (!filterable || !query.trim()) return options
  const needle = query.trim().toLowerCase()
  return options.filter(option => [option.label, option.meta, option.description].filter(Boolean).join(' ').toLowerCase().includes(needle))
}

export function enabledSelectOptions<T extends string>(options: Array<SelectOption<T>>): Array<SelectOption<T>> {
  return options.filter(option => !option.disabled)
}

export function initialSelectIndex<T extends string>(options: Array<SelectOption<T>>, initialValue: T | undefined): number {
  return Math.max(0, options.findIndex(option => option.value === initialValue || option.active))
}

export function selectPageSize(optionCount: number, maxVisible: number | undefined): number {
  return Math.max(1, Math.min(optionCount || 1, maxVisible ?? 6))
}

export function visibleOptionWindow<T extends string>(
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
