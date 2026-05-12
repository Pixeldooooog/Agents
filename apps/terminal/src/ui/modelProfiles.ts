import type {ModelProfile} from '../protocol/types.js'
import type {CommandDef} from './commands.js'

export function isModelProfileQuery(value: string): boolean {
  return /^\/models?\s/.test(value)
}

export function modelProfileMatches(value: string, profiles: ModelProfile[]): CommandDef[] {
  if (!isModelProfileQuery(value)) return []
  const query = value.replace(/^\/models?\s*/, '').trim().toLowerCase()
  return profiles
    .filter(profile => {
      if (!query) return true
      return [profile.name, profile.protocol, profile.model, profile.endpoint]
        .filter(Boolean)
        .some(item => String(item).toLowerCase().includes(query))
    })
    .slice(0, 8)
    .map(profile => ({
      kind: 'model',
      name: profile.name,
      description: `${profile.protocol} · ${profile.model}`,
      argumentHint: profile.endpoint,
      insertText: `/model ${profile.name}`,
      active: profile.active
    }))
}
