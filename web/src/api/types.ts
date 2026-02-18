export interface ReadinessComponent {
  name: string
  value: number | null
  normalized: number
  weight: number
  detail: string
}

export interface Readiness {
  score: number
  label: string
  components: ReadinessComponent[]
}

export interface TodayWorkout {
  discipline: string
  type: string
  target_duration: number | null
  description: string | null
  status: string
}

export interface RaceInfo {
  name: string
  date: string
  distance_type: string
  weeks_out: number
}

export interface Briefing {
  content: string
  alerts: string[] | null
}

export interface DashboardMetrics {
  sleep_score: number | null
  body_battery_wake: number | null
  hrv_last_night: number | null
  resting_hr: number | null
}

export interface DashboardToday {
  date: string
  readiness: Readiness
  today_workout: TodayWorkout | null
  races: RaceInfo[]
  briefing: Briefing | null
  training_status: string | null
  metrics: DashboardMetrics
}

export interface Race {
  id: string
  name: string
  date: string
  distance_type: string
  goal_time: number | null
  notes: string | null
}

export interface Conversation {
  id: string
  title: string | null
  created_at: string
  updated_at: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  tool_calls: Record<string, unknown>[] | null
  created_at: string
}

export interface ChatEvent {
  event: 'token' | 'tool_call' | 'tool_result' | 'done'
  data: Record<string, unknown>
}
