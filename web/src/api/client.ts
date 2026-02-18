import type {
  DashboardToday,
  DashboardWeekly,
  Race,
  Conversation,
  PlannedWorkout,
  Adherence,
  AthleteProfile,
  AthleteBiometrics,
  PersonalRecord,
  GearItem,
} from './types'

const BASE = '/api/v1'

export async function fetchDashboardToday(): Promise<DashboardToday> {
  const res = await fetch(`${BASE}/dashboard/today`)
  if (!res.ok) throw new Error(`Dashboard fetch failed: ${res.status}`)
  return res.json()
}

export async function fetchDashboardWeekly(): Promise<DashboardWeekly> {
  const res = await fetch(`${BASE}/dashboard/weekly`)
  if (!res.ok) throw new Error(`Weekly dashboard fetch failed: ${res.status}`)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const raw: any = await res.json()

  const volume = Object.entries(raw.volume ?? {}).map(([discipline, val]) => {
    const v = val as { hours?: number; distance_km?: number }
    return {
      discipline,
      duration_minutes: Math.round((v.hours ?? 0) * 60),
      distance_km: v.distance_km ?? 0,
    }
  })

  const adh = raw.adherence ?? {}
  const adherence = {
    total: adh.total_planned ?? adh.total ?? 0,
    completed: adh.completed ?? 0,
    missed: adh.missed ?? 0,
    rate: adh.completion_pct ?? adh.rate ?? 0,
  }

  const load_trend = (raw.load_trend ?? []).map(
    (e: { week_start: string; load_7d?: number; load_28d?: number; acute?: number; chronic?: number }) => ({
      week_start: e.week_start,
      acute: e.load_7d ?? e.acute ?? 0,
      chronic: e.load_28d ?? e.chronic ?? 0,
    }),
  )

  return { volume, adherence, load_trend }
}

export async function fetchRaces(): Promise<Race[]> {
  const res = await fetch(`${BASE}/races`)
  if (!res.ok) throw new Error(`Races fetch failed: ${res.status}`)
  return res.json()
}

export async function fetchPlanWorkouts(
  startDate: string,
  endDate: string,
): Promise<PlannedWorkout[]> {
  const res = await fetch(
    `${BASE}/plan/workouts?start_date=${startDate}&end_date=${endDate}`,
  )
  if (!res.ok) throw new Error(`Plan workouts fetch failed: ${res.status}`)
  return res.json()
}

export async function fetchPlanAdherence(
  startDate: string,
  endDate: string,
): Promise<Adherence> {
  const res = await fetch(
    `${BASE}/plan/adherence?start=${startDate}&end=${endDate}`,
  )
  if (!res.ok) throw new Error(`Plan adherence fetch failed: ${res.status}`)
  return res.json()
}

export async function createRace(data: {
  name: string
  date: string
  distance_type: string
  goal_time?: number | null
  notes?: string | null
}): Promise<Race> {
  const res = await fetch(`${BASE}/races`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(`Create race failed: ${res.status}`)
  return res.json()
}

export async function updateRace(
  id: string,
  data: {
    name?: string
    date?: string
    distance_type?: string
    goal_time?: number | null
    notes?: string | null
  },
): Promise<Race> {
  const res = await fetch(`${BASE}/races/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(`Update race failed: ${res.status}`)
  return res.json()
}

export async function deleteRace(id: string): Promise<void> {
  const res = await fetch(`${BASE}/races/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`Delete race failed: ${res.status}`)
}

export async function fetchAthleteProfile(): Promise<AthleteProfile> {
  const res = await fetch(`${BASE}/athlete/profile`)
  if (!res.ok) throw new Error(`Profile fetch failed: ${res.status}`)
  return res.json()
}

export async function fetchAthleteBiometrics(): Promise<AthleteBiometrics> {
  const res = await fetch(`${BASE}/athlete/biometrics`)
  if (!res.ok) throw new Error(`Biometrics fetch failed: ${res.status}`)
  return res.json()
}

export async function fetchAthleteRecords(): Promise<PersonalRecord[]> {
  const res = await fetch(`${BASE}/athlete/records`)
  if (!res.ok) throw new Error(`Records fetch failed: ${res.status}`)
  return res.json()
}

export async function fetchAthleteGear(): Promise<GearItem[]> {
  const res = await fetch(`${BASE}/athlete/gear`)
  if (!res.ok) throw new Error(`Gear fetch failed: ${res.status}`)
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
