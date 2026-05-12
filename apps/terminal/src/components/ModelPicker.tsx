import React, {useEffect, useMemo, useState} from 'react'
import {Box, Text, useStdin} from 'ink'
import figures from 'figures'
import type {ModelProfile} from '../protocol/types.js'
import {colors} from '../ui/theme.js'
import {useSafeInput} from '../hooks/useSafeInput.js'
import {Dialog} from './design/Dialog.js'
import {ShortcutHint} from './design/ShortcutHint.js'

export function ModelPicker({
  profiles,
  onSelect,
  onCancel,
  maxVisible = 10
}: {
  profiles: ModelProfile[]
  onSelect: (name: string) => void
  onCancel: () => void
  maxVisible?: number
}) {
  const visibleProfiles = useMemo(() => profiles.filter(profile => profile.configured !== false), [profiles])
  const rows = visibleProfiles.length ? visibleProfiles : profiles
  const active = rows.find(profile => profile.active)

  return (
    <Dialog
      title="Model Profiles"
      subtitle={active ? `${active.protocol} · ${active.model}` : undefined}
      borderColor={colors.border}
      footer={<ShortcutHint items={[['↑/↓', 'move'], ['enter', 'select'], ['esc', 'cancel']]} />}
    >
      {rows.length ? <ModelPickerList profiles={rows} activeName={active?.name} onSelect={onSelect} onCancel={onCancel} maxVisible={maxVisible} /> : <Text dimColor>No configured model profiles</Text>}
    </Dialog>
  )
}

function ModelPickerList({
  profiles,
  activeName,
  onSelect,
  onCancel,
  maxVisible
}: {
  profiles: ModelProfile[]
  activeName?: string
  onSelect: (name: string) => void
  onCancel: () => void
  maxVisible: number
}) {
  const enabledProfiles = useMemo(() => profiles.filter(profile => profile.configured !== false), [profiles])
  const selectableProfiles = enabledProfiles.length ? enabledProfiles : profiles
  const initialIndex = Math.max(0, selectableProfiles.findIndex(profile => profile.name === activeName || profile.active))
  const [selected, setSelected] = useState(initialIndex)
  const {isRawModeSupported} = useStdin()
  const selectedProfile = selectableProfiles[Math.min(selected, Math.max(0, selectableProfiles.length - 1))]
  const window = visibleModelWindow(profiles, selectedProfile, maxVisible)

  useEffect(() => {
    setSelected(current => Math.min(current, Math.max(0, selectableProfiles.length - 1)))
  }, [selectableProfiles.length])

  useSafeInput((input, key) => {
    const returnKey = key.return || input === '\r' || input === '\n'
    if (key.escape || (key.ctrl && input === 'c')) {
      onCancel()
      return
    }
    if (!selectableProfiles.length) return
    if (key.upArrow || (key.ctrl && input === 'p')) {
      setSelected(current => (current - 1 + selectableProfiles.length) % selectableProfiles.length)
      return
    }
    if (key.downArrow || (key.ctrl && input === 'n')) {
      setSelected(current => (current + 1) % selectableProfiles.length)
      return
    }
    if (key.pageUp) {
      setSelected(current => Math.max(0, current - Math.max(1, Math.min(selectableProfiles.length, maxVisible))))
      return
    }
    if (key.pageDown) {
      setSelected(current => Math.min(Math.max(0, selectableProfiles.length - 1), current + Math.max(1, Math.min(selectableProfiles.length, maxVisible))))
      return
    }
    if (returnKey && selectedProfile && selectedProfile.configured !== false) onSelect(selectedProfile.name)
  }, {isActive: isRawModeSupported})

  return (
    <Box flexDirection="column">
      {window.hiddenBefore ? (
        <Box paddingLeft={3}>
          <Text dimColor>and {window.hiddenBefore} more above...</Text>
        </Box>
      ) : null}
      {window.profiles.map(profile => {
        const index = selectableProfiles.findIndex(item => item.name === profile.name)
        const selectedRow = index === selected && profile.configured !== false
        const muted = profile.configured === false
        return (
          <Box key={profile.name}>
            <Text color={selectedRow ? colors.cyan : muted ? colors.dim : colors.text}>
              {selectedRow ? figures.pointer : ' '} {profile.active ? '●' : ' '} {profile.name.padEnd(20)}
            </Text>
            <Text dimColor>  {profile.protocol} · {profile.model}</Text>
          </Box>
        )
      })}
      {window.hiddenAfter ? (
        <Box paddingLeft={3}>
          <Text dimColor>and {window.hiddenAfter} more...</Text>
        </Box>
      ) : null}
    </Box>
  )
}

function visibleModelWindow(
  profiles: ModelProfile[],
  selectedProfile: ModelProfile | undefined,
  maxVisible: number
): {profiles: ModelProfile[]; hiddenBefore: number; hiddenAfter: number} {
  const visibleCount = Math.max(1, maxVisible)
  if (profiles.length <= visibleCount) return {profiles, hiddenBefore: 0, hiddenAfter: 0}
  const selectedIndex = Math.max(0, selectedProfile ? profiles.findIndex(profile => profile.name === selectedProfile.name) : 0)
  const start = Math.max(0, Math.min(selectedIndex - Math.floor(visibleCount / 2), profiles.length - visibleCount))
  const end = Math.min(profiles.length, start + visibleCount)
  return {profiles: profiles.slice(start, end), hiddenBefore: start, hiddenAfter: profiles.length - end}
}
