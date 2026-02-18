import { useState, useCallback, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchPlanWorkouts, fetchPlanAdherence } from '../api/client'
import WeekCalendar from '../components/plan/WeekCalendar'
import AdherenceBar from '../components/plan/AdherenceBar'

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
  } = useQuery({
    queryKey: ['planWorkouts', startStr, endStr],
    queryFn: () => fetchPlanWorkouts(startStr, endStr),
  })

  const {
    data: adherence,
    isLoading: adherenceLoading,
  } = useQuery({
    queryKey: ['planAdherence', startStr, endStr],
    queryFn: () => fetchPlanAdherence(startStr, endStr),
  })

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
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Training Plan</h1>
        <button
          onClick={() => setWeekStart(getMonday(new Date()))}
          className="text-sm text-blue-400 hover:text-blue-300 transition-colors"
        >
          Today
        </button>
      </div>

      <AdherenceBar adherence={adherence} isLoading={adherenceLoading} />

      <WeekCalendar
        weekStart={weekStart}
        workouts={workouts ?? []}
        isLoading={workoutsLoading}
        onPrevWeek={onPrevWeek}
        onNextWeek={onNextWeek}
      />
    </div>
  )
}
