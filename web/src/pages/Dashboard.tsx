import { useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  fetchDashboardToday,
  fetchDashboardWeekly,
  refreshDashboardData,
} from '../api/client'
import ReadinessCard from '../components/dashboard/ReadinessCard'
import MetricsRow from '../components/dashboard/MetricsRow'
import TodayWorkout from '../components/dashboard/TodayWorkout'
import RaceCountdown from '../components/dashboard/RaceCountdown'
import WeeklyVolume from '../components/dashboard/WeeklyVolume'
import LoadTrend from '../components/dashboard/LoadTrend'
import AlertsList from '../components/dashboard/AlertsList'

function SkeletonCard({ className = '' }: { className?: string }) {
  return (
    <div
      className={`rounded-xl bg-gray-900 border border-gray-800 p-5 animate-pulse ${className}`}
    >
      <div className="h-3 w-24 bg-gray-800 rounded mb-4" />
      <div className="h-8 w-16 bg-gray-800 rounded mb-2" />
      <div className="h-2 w-full bg-gray-800 rounded" />
    </div>
  )
}

export default function Dashboard() {
  const queryClient = useQueryClient()
  const hasTriggeredRefreshRef = useRef(false)

  const refreshMutation = useMutation({
    mutationFn: () => refreshDashboardData(),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard', 'today'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard', 'weekly'] })
    },
  })

  useEffect(() => {
    if (hasTriggeredRefreshRef.current) return
    hasTriggeredRefreshRef.current = true
    refreshMutation.mutate()
  }, [refreshMutation.mutate])

  const today = useQuery({
    queryKey: ['dashboard', 'today'],
    queryFn: fetchDashboardToday,
  })

  const weekly = useQuery({
    queryKey: ['dashboard', 'weekly'],
    queryFn: fetchDashboardWeekly,
  })

  if (today.isLoading) {
    return (
      <div className="p-6 space-y-6 max-w-6xl mx-auto">
        <div className="h-12 w-full bg-gray-900 rounded-xl animate-pulse" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <SkeletonCard className="h-52" />
          <SkeletonCard className="h-52" />
        </div>
      </div>
    )
  }

  if (today.isError) {
    return (
      <div className="p-6 max-w-6xl mx-auto">
        <div className="rounded-xl bg-red-500/10 border border-red-500/20 p-5 text-sm text-red-400">
          Failed to load dashboard data. Please try again later.
        </div>
      </div>
    )
  }

  const data = today.data
  if (!data) return null

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      <div className="rounded-xl bg-gray-900 border border-gray-800 px-5 py-4 text-sm text-gray-300">
        Daily briefing and recommendation approvals now live in the <span className="text-blue-300 font-medium">Coach chat</span>.
      </div>

      {/* Metrics Row */}
      <MetricsRow metrics={data.metrics} trainingStatus={data.training_status} />

      {/* Two-column grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left column */}
        <div className="space-y-6">
          <ReadinessCard readiness={data.readiness} />
          {data.today_workout && <TodayWorkout workout={data.today_workout} />}
          <RaceCountdown races={data.races} />
        </div>

        {/* Right column */}
        <div className="space-y-6">
          {weekly.isError ? (
            <div className="rounded-xl bg-red-500/10 border border-red-500/20 p-5 text-sm text-red-300">
              Could not load weekly volume and load trend.
            </div>
          ) : weekly.data ? (
            <>
              <WeeklyVolume volume={weekly.data.volume} />
              <LoadTrend loadTrend={weekly.data.load_trend} />
            </>
          ) : weekly.isLoading ? (
            <>
              <SkeletonCard className="h-64" />
              <SkeletonCard className="h-64" />
            </>
          ) : null}

          {data.briefing?.alerts && data.briefing.alerts.length > 0 && (
            <AlertsList alerts={data.briefing.alerts} />
          )}
        </div>
      </div>
    </div>
  )
}
