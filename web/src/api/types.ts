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
  readiness_summary: string | null
  workout_recommendation: string | null
  alerts: string[] | null
  recommendation_change?: RecommendationChange | null
}

export type RecommendationDecision = 'approved' | 'rejected' | 'changes_requested'

export interface RecommendationChange {
  id: string
  source: string
  source_ref_id: string | null
  planned_workout_id: string | null
  workout_date: string | null
  recommendation_text: string | null
  proposed_workout: Record<string, unknown> | null
  status: string
  decision_notes: string | null
  requested_changes: string | null
  garmin_sync_status: string | null
  garmin_sync_payload: Record<string, unknown> | null
  garmin_sync_result: Record<string, unknown> | null
  training_impact_log: Record<string, unknown> | null
  created_at: string | null
  decided_at: string | null
  applied_at: string | null
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
  count: number
}

export interface Adherence {
  total: number
  completed: number
  strict_completed?: number
  aligned_substitutions?: number
  due_total?: number
  pending_future?: number
  missed: number
  rate: number
  strict_rate?: number
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

export interface TrendMetricOption {
  key: string
  label: string
  unit: string
}

export interface TrendSeriesPoint {
  date: string
  value: number | null
}

export interface TrendSeriesSummary {
  count: number
  latest: number | null
  min: number | null
  max: number | null
  avg: number | null
  delta: number | null
}

export interface ActivityTypeStat {
  activity_type: string
  count: number
  hours: number
  distance_km: number
  discipline: string
}

export interface TrendEvent {
  date: string
  type: 'race' | 'session' | 'recovery'
  title: string
  detail: string
  level: 'good' | 'watch' | 'warning'
}

export interface TrendCoachSummary {
  headline: string
  bullets: string[]
  recommended_action: string
}

export interface ExecutiveSummary {
  as_of: string
  status_level: 'good' | 'watch' | 'warning'
  status: string
  summary: string
  recommendations: string[]
}

export interface PlanWeekSummary {
  start: string
  end: string
  total_planned: number
  due_so_far: number
  on_plan_completed: number
  remaining: number
  next_sessions: Array<{
    date: string
    label: string
    status: string
  }>
}

export interface CoachInsight {
  level: 'good' | 'watch' | 'warning'
  title: string
  detail: string
}

export interface CoachAnalysis {
  consistency: {
    active_days: number
    period_days: number
    consistency_pct: number
    avg_daily_hours: number
    monotony: number | null
    strain: number | null
  }
  load_management: {
    recent_week_hours: number
    previous_week_hours: number | null
    ramp_hours: number | null
    ramp_pct: number | null
    acwr: number | null
    acwr_band: 'underloaded' | 'balanced' | 'overreaching_risk' | null
    latest_load_7d: number | null
    latest_load_28d: number | null
  }
  recovery_trend: {
    readiness_delta: number | null
    sleep_delta: number | null
    hrv_delta: number | null
    rhr_delta: number | null
  }
  session_profile: {
    session_count: number
    hard_sessions: number
    hard_pct: number | null
    long_sessions: number
    avg_session_duration_min: number | null
    longest_session_min: number | null
  }
  discipline_balance: Record<
    string,
    {
      hours: number
      pct: number
    }
  >
  insights: CoachInsight[]
  totals: {
    total_hours: number
    total_activities: number
  }
}

export interface DashboardTrends {
  start: string
  end: string
  requested_start: string | null
  requested_end: string | null
  range_adjusted: boolean
  earliest_data_date: string | null
  latest_data_date: string | null
  metric: string
  metric_label: string
  metric_unit: string
  metric_options: TrendMetricOption[]
  series: TrendSeriesPoint[]
  series_summary: TrendSeriesSummary
  volume: Record<string, { hours: number; distance_km: number; count: number }>
  activity_types: ActivityTypeStat[]
  stats: {
    total_activities: number
    total_hours: number
    total_distance_km: number
    avg_hr: number | null
  }
  analysis: CoachAnalysis
  events: TrendEvent[]
  coach_summary: TrendCoachSummary | null
  executive_summary: ExecutiveSummary | null
  plan_week: PlanWeekSummary | null
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

export interface ConversationDetail extends Conversation {
  messages: ChatMessage[]
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

export interface PlanActivity {
  id: string
  activity_date: string | null
  start_time: string | null
  name: string | null
  activity_type: string | null
  discipline: string
  duration_seconds: number | null
  distance_meters: number | null
  average_hr: number | null
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
  lactate_threshold_pace: number | null
  cycling_ftp: number | null
}

export interface PersonalRecord {
  id: string
  record_type: string
  activity_type: string
  value: number
  display_value?: string
  value_unit?: string
  value_kind?: string
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
