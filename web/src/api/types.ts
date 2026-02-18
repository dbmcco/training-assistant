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

export interface VolumeEntry {
  discipline: string
  duration_minutes: number
  distance_km: number
}

export interface Adherence {
  total: number
  completed: number
  missed: number
  rate: number
}

export interface LoadTrendEntry {
  week_start: string
  acute: number
  chronic: number
}

export interface DashboardWeekly {
  volume: VolumeEntry[]
  adherence: Adherence
  load_trend: LoadTrendEntry[]
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

export interface PlannedWorkout {
  id: string
  plan_id: string
  date: string
  discipline: string
  workout_type: string
  target_duration: number | null
  target_distance: number | null
  target_hr_zone: string | null
  description: string | null
  status: string
}

export interface AthleteProfile {
  id: string
  notes: Record<string, unknown> | null
  goals: string | null
  injury_history: string | null
  preferences: Record<string, unknown> | null
  updated_at: string | null
}

export interface AthleteBiometrics {
  id: string
  date: string | null
  weight_kg: number | null
  body_fat_pct: number | null
  muscle_mass_kg: number | null
  bmi: number | null
  fitness_age: number | null
  actual_age: number | null
  lactate_threshold_hr: number | null
  lactate_threshold_pace: string | null
  cycling_ftp: number | null
}

export interface PersonalRecord {
  id: string
  record_type: string
  activity_type: string
  value: number
  activity_id: number | null
  recorded_at: string | null
}

export interface GearItem {
  id: string
  garmin_gear_uuid: string
  name: string | null
  gear_type: string
  brand: string | null
  model: string | null
  date_begin: string | null
  max_distance_km: number | null
  total_distance_km: number | null
  total_activities: number | null
}
