import { useState, useCallback, useMemo, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  fetchPlanActivities,
  fetchPlanWorkouts,
  fetchPlanAdherence,
  fetchPlanChanges,
  refreshDashboardData,
} from '../api/client'
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

function formatTimestamp(value: string | null): string {
  if (!value) return ''
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export default function Plan() {
  const queryClient = useQueryClient()
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

  const {
    data: recentChanges,
    isLoading: changesLoading,
    isError: changesError,
  } = useQuery({
    queryKey: ['planChanges'],
    queryFn: () => fetchPlanChanges({ daysBack: 7, limit: 12 }),
  })

  const refreshMutation = useMutation({
    mutationFn: () => refreshDashboardData({ includeCalendar: true, force: true }),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['planWorkouts'] })
      queryClient.invalidateQueries({ queryKey: ['planAdherence'] })
      queryClient.invalidateQueries({ queryKey: ['planActivities'] })
      queryClient.invalidateQueries({ queryKey: ['planChanges'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard', 'today'] })
    },
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
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => refreshMutation.mutate()}
            disabled={refreshMutation.isPending}
            className="rounded-lg border border-gray-700 px-3 py-1.5 text-xs text-gray-200 hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {refreshMutation.isPending ? 'Refreshing...' : 'Refresh Garmin'}
          </button>
          <button
            onClick={() => setWeekStart(getMonday(new Date()))}
            className="text-sm text-blue-400 hover:text-blue-300 transition-colors"
          >
            Today
          </button>
        </div>
      </div>

      <AdherenceBar adherence={adherence} isLoading={adherenceLoading} />

      {changesError ? (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-200">
          Could not load Garmin plan change history.
        </div>
      ) : (
        <div className="rounded-xl border border-gray-800 bg-gray-900 px-4 py-3">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-200">Recent Garmin Changes</h2>
            <span className="text-[11px] text-gray-500">Last 7 days</span>
          </div>
          {changesLoading ? (
            <p className="text-xs text-gray-500">Loading changes...</p>
          ) : recentChanges && recentChanges.length > 0 ? (
            <div className="space-y-1.5">
              {recentChanges.slice(0, 6).map((change) => (
                <div
                  key={change.id}
                  className="rounded-md border border-gray-800 bg-gray-950/60 px-3 py-2"
                >
                  <p className="text-xs text-gray-200">{change.summary}</p>
                  <p className="text-[11px] text-gray-500">
                    {formatTimestamp(change.detected_at)}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-gray-500">
              No adaptive-plan changes detected recently.
            </p>
          )}
        </div>
      )}

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
