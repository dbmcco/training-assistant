import type { DashboardToday, Race, Conversation } from './types'

const BASE = '/api/v1'

export async function fetchDashboardToday(): Promise<DashboardToday> {
  const res = await fetch(`${BASE}/dashboard/today`)
  if (!res.ok) throw new Error(`Dashboard fetch failed: ${res.status}`)
  return res.json()
}

export async function fetchRaces(): Promise<Race[]> {
  const res = await fetch(`${BASE}/races`)
  if (!res.ok) throw new Error(`Races fetch failed: ${res.status}`)
  return res.json()
}

export async function fetchConversations(): Promise<Conversation[]> {
  const res = await fetch(`${BASE}/conversations`)
  if (!res.ok) throw new Error(`Conversations fetch failed: ${res.status}`)
  return res.json()
}

export async function* streamChat(
  message: string,
  conversationId?: string,
  viewContext?: Record<string, unknown>,
): AsyncGenerator<{ event: string; data: Record<string, unknown> }> {
  const res = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
      view_context: viewContext,
    }),
  })

  if (!res.ok) throw new Error(`Chat failed: ${res.status}`)
  if (!res.body) throw new Error('No response body')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        // SSE event type line — next data line has the payload
        continue
      }
      if (line.startsWith('data: ')) {
        try {
          yield JSON.parse(line.slice(6))
        } catch {
          // skip malformed JSON
        }
      }
    }
  }
}
