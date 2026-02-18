import { useMemo } from 'react'
import type { PlannedWorkout } from '../../api/types'
import WorkoutCard from './WorkoutCard'

const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as const

interface WeekCalendarProps {
  weekStart: Date
  workouts: PlannedWorkout[]
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

export default function WeekCalendar({
  weekStart,
  workouts,
  isLoading,
  onPrevWeek,
  onNextWeek,
}: WeekCalendarProps) {
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

  const weekEnd = days[days.length - 1].date

  return (
    <div>
      {/* Week nav header */}
      <div className="flex items-center justify-between mb-4">
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
        <h2 className="text-sm font-semibold text-gray-300">
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

      {/* 7-day grid */}
      <div className="grid grid-cols-7 gap-2">
        {days.map((day) => {
          const dayWorkouts = workoutsByDate[day.dateStr] ?? []
          const today = isToday(day.date)

          return (
            <div
              key={day.dateStr}
              className={`rounded-xl border p-3 min-h-[140px] transition-colors ${
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
              ) : dayWorkouts.length === 0 ? (
                <p className="text-xs text-gray-700 italic mt-4 text-center">
                  Rest
                </p>
              ) : (
                <div className="space-y-2">
                  {dayWorkouts.map((w) => (
                    <WorkoutCard key={w.id} workout={w} />
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
