import type {
  Briefing,
  DashboardToday,
  DashboardWeekly,
  DashboardTrends,
  Race,
  Conversation,
  PlannedWorkout,
  AssistantPlanGenerationResult,
  PlanChangeEvent,
  PlanActivity,
  Adherence,
  AthleteProfile,
  AthleteBiometrics,
  PersonalRecord,
  GearItem,
  RecommendationChange,
  RecommendationDecision,
  ConversationDetail,
} from './types'

const BASE = '/api/v1'
const REQUEST_TIMEOUT_MS = 12_000
const CHAT_STREAM_IDLE_TIMEOUT_MS = 45_000

async function fetchWithTimeout(
  input: RequestInfo | URL,
  init?: RequestInit,
  timeoutMs = REQUEST_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController()
  const timeoutId = globalThis.setTimeout(() => controller.abort(), timeoutMs)

  try {
    return await fetch(input, {
      ...init,
      signal: controller.signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s`)
    }
    throw error
  } finally {
    globalThis.clearTimeout(timeoutId)
  }
}

export async function fetchDashboardToday(): Promise<DashboardToday> {
  const res = await fetchWithTimeout(`${BASE}/dashboard/today`)
  if (!res.ok) throw new Error(`Dashboard fetch failed: ${res.status}`)
  return res.json()
}

export async function refreshDashboardData(options?: {
  includeCalendar?: boolean
  force?: boolean
}): Promise<{
  status: string
  reason?: string
}> {
  const params = new URLSearchParams()
  if (options?.includeCalendar) params.set('include_calendar', 'true')
  if (options?.force) params.set('force', 'true')
  const suffix = params.toString() ? `?${params.toString()}` : ''
  const res = await fetchWithTimeout(
    `${BASE}/dashboard/refresh${suffix}`,
    { method: 'POST' },
    45_000,
  )
  if (!res.ok) throw new Error(`Dashboard refresh failed: ${res.status}`)
  return res.json()
}

export async function fetchDashboardWeekly(): Promise<DashboardWeekly> {
  const res = await fetchWithTimeout(`${BASE}/dashboard/weekly`)
  if (!res.ok) throw new Error(`Weekly dashboard fetch failed: ${res.status}`)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const raw: any = await res.json()

  const volume = Object.entries(raw.volume ?? {}).map(([discipline, val]) => {
    const v = val as { hours?: number; distance_km?: number; count?: number }
    return {
      discipline,
      duration_minutes: Math.round((v.hours ?? 0) * 60),
      distance_km: v.distance_km ?? 0,
      count: v.count ?? 0,
    }
  })

  const adh = raw.adherence ?? {}
  const adherence = {
    total: adh.total_planned ?? adh.total ?? 0,
    completed: adh.completed ?? 0,
    strict_completed: adh.strict_completed ?? adh.completed ?? 0,
    aligned_substitutions: adh.aligned_substitutions ?? 0,
    due_total: adh.due_planned ?? adh.total_planned ?? adh.total ?? 0,
    pending_future: adh.pending_future ?? 0,
    missed: adh.missed ?? 0,
    rate: adh.completion_pct != null ? adh.completion_pct / 100 : adh.rate ?? 0,
    strict_rate:
      adh.strict_completion_pct != null ? adh.strict_completion_pct / 100 : undefined,
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

export async function fetchDashboardTrends(
  startDate: string,
  endDate: string,
  metric: string,
): Promise<DashboardTrends> {
  const params = new URLSearchParams({
    start: startDate,
    end: endDate,
    metric,
  })
  const res = await fetchWithTimeout(`${BASE}/dashboard/trends?${params.toString()}`)
  if (!res.ok) throw new Error(`Trends dashboard fetch failed: ${res.status}`)
  return res.json()
}

export async function fetchRaces(): Promise<Race[]> {
  const res = await fetchWithTimeout(`${BASE}/races`)
  if (!res.ok) throw new Error(`Races fetch failed: ${res.status}`)
  return res.json()
}

export async function fetchPlanWorkouts(
  startDate: string,
  endDate: string,
): Promise<PlannedWorkout[]> {
  const res = await fetchWithTimeout(
    `${BASE}/plan/workouts?start_date=${startDate}&end_date=${endDate}`,
  )
  if (!res.ok) throw new Error(`Plan workouts fetch failed: ${res.status}`)
  return res.json()
}

export async function fetchPlanAdherence(
  startDate: string,
  endDate: string,
): Promise<Adherence> {
  const res = await fetchWithTimeout(
    `${BASE}/plan/adherence?start=${startDate}&end=${endDate}`,
  )
  if (!res.ok) throw new Error(`Plan adherence fetch failed: ${res.status}`)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const raw: any = await res.json()
  return {
    total: raw.total_planned ?? raw.total ?? 0,
    completed: raw.completed ?? 0,
    strict_completed: raw.strict_completed ?? raw.completed ?? 0,
    aligned_substitutions: raw.aligned_substitutions ?? 0,
    due_total: raw.due_planned ?? raw.total_planned ?? raw.total ?? 0,
    pending_future: raw.pending_future ?? 0,
    missed: raw.missed ?? 0,
    rate: raw.completion_pct != null ? raw.completion_pct / 100 : raw.rate ?? 0,
    strict_rate:
      raw.strict_completion_pct != null ? raw.strict_completion_pct / 100 : undefined,
  }
}

export async function fetchPlanChanges(options?: {
  daysBack?: number
  limit?: number
}): Promise<PlanChangeEvent[]> {
  const params = new URLSearchParams()
  if (options?.daysBack != null) params.set('days_back', String(options.daysBack))
  if (options?.limit != null) params.set('limit', String(options.limit))
  const suffix = params.toString() ? `?${params.toString()}` : ''
  const res = await fetchWithTimeout(`${BASE}/plan/changes${suffix}`)
  if (!res.ok) throw new Error(`Plan changes fetch failed: ${res.status}`)
  return res.json()
}

export async function generateAssistantPlan(options?: {
  daysAhead?: number
  overwrite?: boolean
  syncToGarmin?: boolean
}): Promise<AssistantPlanGenerationResult> {
  const params = new URLSearchParams()
  if (options?.daysAhead != null) params.set('days_ahead', String(options.daysAhead))
  if (options?.overwrite != null) params.set('overwrite', String(options.overwrite))
  if (options?.syncToGarmin != null) params.set('sync_to_garmin', String(options.syncToGarmin))
  const suffix = params.toString() ? `?${params.toString()}` : ''
  const res = await fetchWithTimeout(`${BASE}/plan/assistant/generate${suffix}`, {
    method: 'POST',
  }, 90_000)
  if (!res.ok) throw new Error(`Assistant plan generation failed: ${res.status}`)
  return res.json()
}

export async function fetchPlanActivities(
  startDate: string,
  endDate: string,
): Promise<PlanActivity[]> {
  const res = await fetchWithTimeout(
    `${BASE}/plan/activities?start_date=${startDate}&end_date=${endDate}`,
  )
  if (!res.ok) throw new Error(`Plan activities fetch failed: ${res.status}`)
  return res.json()
}

export async function createRace(data: {
  name: string
  date: string
  distance_type: string
  goal_time?: number | null
  notes?: string | null
}): Promise<Race> {
  const res = await fetchWithTimeout(`${BASE}/races`, {
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
  const res = await fetchWithTimeout(`${BASE}/races/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(`Update race failed: ${res.status}`)
  return res.json()
}

export async function deleteRace(id: string): Promise<void> {
  const res = await fetchWithTimeout(`${BASE}/races/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`Delete race failed: ${res.status}`)
}

export async function fetchAthleteProfile(): Promise<AthleteProfile> {
  const res = await fetchWithTimeout(`${BASE}/athlete/profile`)
  if (!res.ok) throw new Error(`Profile fetch failed: ${res.status}`)
  return res.json()
}

export async function fetchAthleteBiometrics(): Promise<AthleteBiometrics> {
  const res = await fetchWithTimeout(`${BASE}/athlete/biometrics`)
  if (!res.ok) throw new Error(`Biometrics fetch failed: ${res.status}`)
  return res.json()
}

export async function fetchAthleteRecords(): Promise<PersonalRecord[]> {
  const res = await fetchWithTimeout(`${BASE}/athlete/records`)
  if (!res.ok) throw new Error(`Records fetch failed: ${res.status}`)
  return res.json()
}

export async function fetchAthleteGear(): Promise<GearItem[]> {
  const res = await fetchWithTimeout(`${BASE}/athlete/gear`)
  if (!res.ok) throw new Error(`Gear fetch failed: ${res.status}`)
  return res.json()
}

export async function generateBriefing(): Promise<Briefing> {
  const res = await fetchWithTimeout(`${BASE}/briefings/generate`, { method: 'POST' })
  if (!res.ok) throw new Error(`Briefing generation failed: ${res.status}`)
  return res.json()
}

export async function submitRecommendationDecision(
  recommendationId: string,
  payload: {
    decision: RecommendationDecision
    note?: string
    requested_changes?: string
  },
): Promise<RecommendationChange> {
  const res = await fetchWithTimeout(`${BASE}/recommendations/${recommendationId}/decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(`Recommendation decision failed: ${res.status}`)
  return res.json()
}

export async function fetchRecommendations(options?: {
  status?: string
  limit?: number
}): Promise<RecommendationChange[]> {
  const params = new URLSearchParams()
  if (options?.status) params.set('status', options.status)
  if (options?.limit) params.set('limit', String(options.limit))
  const suffix = params.toString() ? `?${params.toString()}` : ''
  const res = await fetchWithTimeout(`${BASE}/recommendations${suffix}`)
  if (!res.ok) throw new Error(`Recommendations fetch failed: ${res.status}`)
  return res.json()
}

export async function fetchConversations(): Promise<Conversation[]> {
  const res = await fetchWithTimeout(`${BASE}/conversations`)
  if (!res.ok) throw new Error(`Conversations fetch failed: ${res.status}`)
  return res.json()
}

export async function fetchConversation(
  conversationId: string,
  options?: {
    limit?: number
    before?: string
  },
): Promise<ConversationDetail> {
  const params = new URLSearchParams()
  if (options?.limit != null) params.set('limit', String(options.limit))
  if (options?.before) params.set('before', options.before)
  const suffix = params.toString() ? `?${params.toString()}` : ''
  const res = await fetchWithTimeout(`${BASE}/conversations/${conversationId}${suffix}`)
  if (!res.ok) throw new Error(`Conversation fetch failed: ${res.status}`)
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
  let currentEvent = 'message'

  const parseData = (
    payload: string,
  ): { event: string; data: Record<string, unknown> } | null => {
    try {
      let parsed: unknown = JSON.parse(payload)
      if (typeof parsed === 'string') {
        try {
          parsed = JSON.parse(parsed)
        } catch {
          parsed = { raw: parsed }
        }
      }
      return {
        event: currentEvent,
        data: (parsed as Record<string, unknown>) ?? {},
      }
    } catch {
      return null
    } finally {
      currentEvent = 'message'
    }
  }

  const readWithIdleTimeout = async () => {
    return new Promise<ReadableStreamReadResult<Uint8Array>>((resolve, reject) => {
      const timeoutId = globalThis.setTimeout(() => {
        reject(new Error('Chat stream timed out waiting for data'))
      }, CHAT_STREAM_IDLE_TIMEOUT_MS)
      reader
        .read()
        .then((result) => {
          globalThis.clearTimeout(timeoutId)
          resolve(result)
        })
        .catch((error) => {
          globalThis.clearTimeout(timeoutId)
          reject(error)
        })
    })
  }

  while (true) {
    const { done, value } = await readWithIdleTimeout()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim() || 'message'
        continue
      }
      if (line.startsWith('data: ')) {
        const evt = parseData(line.slice(6))
        if (evt) {
          yield evt
        }
      }
    }
  }

  // Process trailing line when stream ends without final newline.
  const lastLine = buffer.trim()
  if (lastLine.startsWith('data: ')) {
    const evt = parseData(lastLine.slice(6))
    if (evt) {
      yield evt
    }
  }
}
