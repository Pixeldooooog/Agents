import type {SessionRecord} from '../protocol/types.js'

export function sessionTableRows(sessions: SessionRecord[]): Array<[string, string]> {
  if (!sessions.length) return [['sessions', 'none']]
  return sessions.map(session => [
    session.short_id,
    `${session.updated} · ${session.messages} messages · ${session.model}${session.workspace ? ` · ${session.workspace}` : ''}`
  ])
}
