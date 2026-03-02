import { useState, useCallback, useMemo, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchPlanActivities, fetchPlanWorkouts, fetchPlanAdherence } from '../api/client'
import WeekCalendar from '../components/plan/WeekCalendar'
import AdherenceBar from '../components/plan/AdherenceBar'
import Races from './Races'

function getMonday(d: Date): Date {
  const date = new Date(d)
  const day = date.getDay()
  // getDay(): 0=Sun, 1=Mon, ... 6=Sat
  const diff = day === 0 ? -6 : 1 - day
  date.setDate(date.getDate() + diff)
  date.setHours(0, 0, 0, 0)
  return date
}

function formatDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

export default function Plan() {
  const [weekStart, setWeekStart] = useState<Date>(() => getMonday(new Date()))
  const currentWeekStartStr = useMemo(() => formatDate(getMonday(new Date())), [])
  const todayStart = useMemo(() => {
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    return d
  }, [])

  const weekEnd = useMemo(() => {
    const end = new Date(weekStart)
    end.setDate(end.getDate() + 6)
    return end
  }, [weekStart])

  const startStr = formatDate(weekStart)
  const endStr = formatDate(weekEnd)

  const {
    data: workouts,
    isLoading: workoutsLoading,
    isError: workoutsError,
  } = useQuery({
    queryKey: ['planWorkouts', startStr, endStr],
    queryFn: () => fetchPlanWorkouts(startStr, endStr),
  })

  const {
    data: adherence,
    isLoading: adherenceLoading,
    isError: adherenceError,
  } = useQuery({
    queryKey: ['planAdherence', startStr, endStr],
    queryFn: () => fetchPlanAdherence(startStr, endStr),
  })

  const {
    data: activities,
    isLoading: activitiesLoading,
    isError: activitiesError,
  } = useQuery({
    queryKey: ['planActivities', startStr, endStr],
    queryFn: () => fetchPlanActivities(startStr, endStr),
  })

  const atAGlance = useMemo(() => {
    const planned = (workouts ?? []).length
    const done = adherence?.completed ?? (activities ?? []).length
    const due = adherence?.due_total ?? planned
    return {
      planned,
      due,
      done,
      completionPct: due > 0 ? Math.round((done / due) * 100) : 0,
    }
  }, [workouts, activities, adherence])

  const hasQueryError = workoutsError || adherenceError || activitiesError

  useEffect(() => {
    if (workoutsLoading || workoutsError || !workouts) {
      return
    }

    const viewingCurrentWeek = formatDate(weekStart) === currentWeekStartStr
    if (!viewingCurrentWeek) {
      return
    }

    const hasRemainingThisWeek = workouts.some((workout) => {
      const status = (workout.status ?? '').toLowerCase()
      const isRemainingStatus = status === '' || status === 'upcoming' || status === 'modified'
      if (!isRemainingStatus) {
        return false
      }
      const workoutDate = new Date(`${workout.date}T00:00:00`)
      return workoutDate >= todayStart
    })

    if (!hasRemainingThisWeek) {
      setWeekStart((prev) => {
        const next = new Date(prev)
        next.setDate(next.getDate() + 7)
        return next
      })
    }
  }, [workoutsLoading, workoutsError, workouts, weekStart, currentWeekStartStr, todayStart])

  const onPrevWeek = useCallback(() => {
    setWeekStart((prev) => {
      const d = new Date(prev)
      d.setDate(d.getDate() - 7)
      return d
    })
  }, [])

  const onNextWeek = useCallback(() => {
    setWeekStart((prev) => {
      const d = new Date(prev)
      d.setDate(d.getDate() + 7)
      return d
    })
  }, [])

  return (
    <div className="p-6 space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Plan & Races</h1>
        <button
          onClick={() => setWeekStart(getMonday(new Date()))}
          className="text-sm text-blue-400 hover:text-blue-300 transition-colors"
        >
          Today
        </button>
      </div>

      <AdherenceBar adherence={adherence} isLoading={adherenceLoading} />

      {hasQueryError && (
        <div className="rounded-xl bg-amber-500/10 border border-amber-500/30 px-4 py-3 text-xs text-amber-200">
          Some plan data failed to load. Showing available data.
        </div>
      )}

      <div className="grid grid-cols-3 gap-2">
        <div className="rounded-lg bg-gray-900 border border-gray-800 px-3 py-2">
          <div className="text-[11px] text-gray-500">Planned</div>
          <div className="text-sm font-semibold text-gray-200">{atAGlance.planned}</div>
        </div>
        <div className="rounded-lg bg-gray-900 border border-gray-800 px-3 py-2">
          <div className="text-[11px] text-gray-500">Done</div>
          <div className="text-sm font-semibold text-emerald-300">{atAGlance.done}</div>
        </div>
        <div className="rounded-lg bg-gray-900 border border-gray-800 px-3 py-2">
          <div className="text-[11px] text-gray-500">On Plan vs Due</div>
          <div className="text-sm font-semibold text-gray-200">{atAGlance.completionPct}%</div>
        </div>
      </div>

      <WeekCalendar
        weekStart={weekStart}
        workouts={workouts ?? []}
        activities={activities ?? []}
        isLoading={workoutsLoading || activitiesLoading}
        onPrevWeek={onPrevWeek}
        onNextWeek={onNextWeek}
      />

      <div className="border-t border-gray-800 pt-6">
        <Races embedded />
      </div>
    </div>
  )
}
