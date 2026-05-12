import type {TranscriptItem} from '../components/MessageList.js'

export type SessionTranscriptMessage = {
  role: string
  content: string
}

export function transcriptFromSession(messages: SessionTranscriptMessage[]): TranscriptItem[] {
  return messages.flatMap(message => {
    if (message.role === 'user') return [{kind: 'user', text: message.content} as TranscriptItem]
    if (message.role === 'assistant') return [{kind: 'assistant', text: message.content} as TranscriptItem]
    if (message.role === 'tool') return [{kind: 'status', label: 'tool', text: message.content} as TranscriptItem]
    return []
  })
}
