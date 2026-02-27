import { useEffect, useMemo, useRef, useState } from 'react'
import type { PlanActivity, PlannedWorkout } from '../../api/types'
import WorkoutCard from './WorkoutCard'
import { formatDistanceFromMeters } from '../../utils/units'

const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as const

interface WeekCalendarProps {
  weekStart: Date
  workouts: PlannedWorkout[]
  activities: PlanActivity[]
  isLoading: boolean
  onPrevWeek: () => void
  onNextWeek: () => void
}

function formatDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function formatMonthDay(d: Date): string {
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function isToday(d: Date): boolean {
  const now = new Date()
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  )
}

function formatDoneDuration(seconds: number | null): string {
  if (seconds == null || seconds <= 0) return ''
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return m > 0 ? `${h}h ${m}m` : `${h}h`
}

function normalizePlannedDurationMinutes(rawDuration: number | null): number | null {
  if (rawDuration == null || rawDuration <= 0) return null
  // Garmin planned workouts arrive in seconds; user-entered edits may already be minutes.
  return rawDuration >= 600 ? Math.round(rawDuration / 60) : rawDuration
}

function formatDuration(rawDuration: number | null): string {
  const minutes = normalizePlannedDurationMinutes(rawDuration)
  if (minutes == null || minutes <= 0) return '-'
  if (minutes < 60) return `${minutes}m`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return m > 0 ? `${h}h ${m}m` : `${h}h`
}

function prettyLabel(value: string | null | undefined): string {
  if (!value) return '-'
  return value.replace(/_/g, ' ')
}

export default function WeekCalendar({
  weekStart,
  workouts,
  activities,
  isLoading,
  onPrevWeek,
  onNextWeek,
}: WeekCalendarProps) {
  const scrollerRef = useRef<HTMLDivElement | null>(null)
  const [selectedWorkout, setSelectedWorkout] = useState<PlannedWorkout | null>(null)

  const days = useMemo(() => {
    return DAY_LABELS.map((label, i) => {
      const d = new Date(weekStart)
      d.setDate(d.getDate() + i)
      return { label, date: d, dateStr: formatDate(d) }
    })
  }, [weekStart])

  const workoutsByDate = useMemo(() => {
    const map: Record<string, PlannedWorkout[]> = {}
    for (const w of workouts) {
      if (!map[w.date]) map[w.date] = []
      map[w.date].push(w)
    }
    return map
  }, [workouts])

  const activitiesByDate = useMemo(() => {
    const map: Record<string, PlanActivity[]> = {}
    for (const a of activities) {
      if (!a.activity_date) continue
      if (!map[a.activity_date]) map[a.activity_date] = []
      map[a.activity_date].push(a)
    }
    return map
  }, [activities])

  const weekEnd = days[days.length - 1].date

  useEffect(() => {
    const todayCard = scrollerRef.current?.querySelector<HTMLElement>(
      '[data-is-today="true"]',
    )
    if (todayCard) {
      todayCard.scrollIntoView({
        behavior: 'smooth',
        block: 'nearest',
        inline: 'start',
      })
    }
  }, [weekStart])

  useEffect(() => {
    if (!selectedWorkout) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setSelectedWorkout(null)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [selectedWorkout])

  return (
    <div>
      {/* Week nav header */}
      <div className="mb-4 flex items-center justify-between">
        <button
          onClick={onPrevWeek}
          className="p-2 rounded-lg text-gray-400 hover:text-gray-200 hover:bg-gray-800 transition-colors"
          aria-label="Previous week"
        >
          <svg className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
            <path
              fillRule="evenodd"
              d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z"
              clipRule="evenodd"
            />
          </svg>
        </button>
        <h2 className="text-xs font-semibold text-gray-300 sm:text-sm">
          {formatMonthDay(weekStart)} &mdash; {formatMonthDay(weekEnd)}
        </h2>
        <button
          onClick={onNextWeek}
          className="p-2 rounded-lg text-gray-400 hover:text-gray-200 hover:bg-gray-800 transition-colors"
          aria-label="Next week"
        >
          <svg className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
            <path
              fillRule="evenodd"
              d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z"
              clipRule="evenodd"
            />
          </svg>
        </button>
      </div>

      {/* 7-day grid — horizontal scroll on mobile, grid on desktop */}
      <div
        ref={scrollerRef}
        className="flex gap-2 overflow-x-auto snap-x snap-mandatory pb-3 -mx-2 px-2 md:mx-0 md:grid md:grid-cols-7 md:overflow-visible md:px-0 md:pb-0"
      >
        {days.map((day) => {
          const dayWorkouts = workoutsByDate[day.dateStr] ?? []
          const dayActivities = activitiesByDate[day.dateStr] ?? []
          const today = isToday(day.date)

          return (
            <div
              key={day.dateStr}
              data-is-today={today ? 'true' : undefined}
              className={`min-h-[180px] w-[84vw] max-w-[320px] shrink-0 snap-start rounded-xl border p-3 transition-colors sm:w-[280px] sm:max-w-none md:min-h-[160px] md:w-auto md:min-w-0 md:shrink ${
                today
                  ? 'border-blue-500/50 bg-blue-500/5'
                  : 'border-gray-800 bg-gray-900'
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium text-gray-500">
                  {day.label}
                </span>
                <span
                  className={`text-xs font-semibold ${
                    today ? 'text-blue-400' : 'text-gray-400'
                  }`}
                >
                  {day.date.getDate()}
                </span>
              </div>

              {isLoading ? (
                <div className="space-y-2 animate-pulse">
                  <div className="h-16 bg-gray-800 rounded-lg" />
                </div>
              ) : (
                <div className="space-y-2 overflow-hidden">
                  <div>
                    <div className="text-[10px] uppercase tracking-wide text-gray-500 mb-1">
                      Planned
                    </div>
                    {dayWorkouts.length === 0 ? (
                      <p className="text-[11px] text-gray-700 italic text-center py-1">
                        Rest
                      </p>
                    ) : (
                      <div className="space-y-2">
                        {dayWorkouts.map((w) => (
                          <WorkoutCard key={w.id} workout={w} onClick={setSelectedWorkout} />
                        ))}
                      </div>
                    )}
                  </div>
                  <div>
                    <div className="text-[10px] uppercase tracking-wide text-gray-500 mb-1">
                      Done
                    </div>
                    {dayActivities.length === 0 ? (
                      <p className="text-[11px] text-gray-700 italic text-center py-1">
                        None
                      </p>
                    ) : (
                      <div className="space-y-1.5">
                        {dayActivities.map((a) => (
                          <div
                            key={a.id}
                            className="rounded-md border border-emerald-500/20 bg-emerald-500/10 px-2 py-1.5 overflow-hidden"
                          >
                            <div className="text-[10px] uppercase tracking-wide text-emerald-300 truncate">
                              {a.discipline}
                            </div>
                            <div className="text-xs text-emerald-100 font-medium truncate">
                              {a.name || a.activity_type || 'Activity'}
                            </div>
                            <div className="text-[11px] text-emerald-200/80">
                              {formatDoneDuration(a.duration_seconds)}
                              {a.distance_meters != null && a.distance_meters > 0
                                ? ` • ${formatDistanceFromMeters(a.distance_meters, a.discipline)}`
                                : ''}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {selectedWorkout && (
        <div className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-4">
          <button
            type="button"
            className="absolute inset-0 bg-black/70"
            aria-label="Close workout details"
            onClick={() => setSelectedWorkout(null)}
          />
          <div
            className="relative z-10 max-h-[88dvh] w-full max-w-xl overflow-hidden rounded-t-2xl border border-gray-700 bg-gray-900 shadow-2xl sm:rounded-xl"
            role="dialog"
            aria-modal="true"
            aria-label="Workout details"
          >
            <div className="sticky top-0 z-10 flex items-center justify-between border-b border-gray-800 bg-gray-900 px-4 py-3">
              <h3 className="text-sm font-semibold text-gray-100">Workout Details</h3>
              <button
                type="button"
                className="rounded-lg border border-gray-700 px-2 py-1 text-xs text-gray-300 hover:bg-gray-800"
                onClick={() => setSelectedWorkout(null)}
              >
                Close
              </button>
            </div>
            <dl className="grid max-h-[calc(88dvh-56px)] grid-cols-1 gap-x-3 gap-y-2 overflow-y-auto px-4 py-4 text-sm sm:grid-cols-[120px_1fr]">
              <dt className="text-gray-500 text-xs sm:text-sm">Date</dt>
              <dd className="text-gray-100">{selectedWorkout.date}</dd>

              <dt className="text-gray-500 text-xs sm:text-sm">Discipline</dt>
              <dd className="text-gray-100 capitalize">{prettyLabel(selectedWorkout.discipline)}</dd>

              <dt className="text-gray-500 text-xs sm:text-sm">Workout</dt>
              <dd className="text-gray-100 capitalize">{prettyLabel(selectedWorkout.workout_type)}</dd>

              <dt className="text-gray-500 text-xs sm:text-sm">Status</dt>
              <dd className="text-gray-100 capitalize">{prettyLabel(selectedWorkout.status)}</dd>

              <dt className="text-gray-500 text-xs sm:text-sm">Duration</dt>
              <dd className="text-gray-100">{formatDuration(selectedWorkout.target_duration)}</dd>

              <dt className="text-gray-500 text-xs sm:text-sm">Distance</dt>
              <dd className="text-gray-100">
                {formatDistanceFromMeters(selectedWorkout.target_distance, selectedWorkout.discipline)}
              </dd>

              <dt className="text-gray-500 text-xs sm:text-sm">HR Zone</dt>
              <dd className="text-gray-100 uppercase">{prettyLabel(selectedWorkout.target_hr_zone)}</dd>

              <dt className="text-gray-500 text-xs sm:text-sm">Description</dt>
              <dd className="text-gray-100 whitespace-pre-wrap">
                {selectedWorkout.description ?? '-'}
              </dd>

              <dt className="text-gray-500 text-xs sm:text-sm">Workout ID</dt>
              <dd className="text-xs text-gray-400 break-all">{selectedWorkout.id}</dd>
            </dl>
          </div>
        </div>
      )}
    </div>
  )
}
