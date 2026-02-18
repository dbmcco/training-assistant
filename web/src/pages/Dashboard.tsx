import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchDashboardToday, fetchDashboardWeekly, generateBriefing } from '../api/client'
import type { Briefing } from '../api/types'
import BriefingBanner from '../components/dashboard/BriefingBanner'
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

  const today = useQuery({
    queryKey: ['dashboard', 'today'],
    queryFn: fetchDashboardToday,
  })

  const weekly = useQuery({
    queryKey: ['dashboard', 'weekly'],
    queryFn: fetchDashboardWeekly,
  })

  const briefingMutation = useMutation({
    mutationFn: generateBriefing,
    onSuccess: (briefing: Briefing) => {
      queryClient.setQueryData(['dashboard', 'today'], (old: typeof today.data) =>
        old ? { ...old, briefing } : old,
      )
    },
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
      {/* Briefing Banner */}
      {data.briefing ? (
        <BriefingBanner briefing={data.briefing} />
      ) : (
        <button
          onClick={() => briefingMutation.mutate()}
          disabled={briefingMutation.isPending}
          className="w-full rounded-xl bg-gray-900 border border-gray-800 px-5 py-3 text-left hover:bg-gray-800/40 transition-colors flex items-center gap-2 disabled:opacity-50"
        >
          <svg className="w-5 h-5 text-blue-400 shrink-0" viewBox="0 0 20 20" fill="currentColor">
            <path d="M11 3a1 1 0 10-2 0v1a1 1 0 102 0V3zM15.657 5.757a1 1 0 00-1.414-1.414l-.707.707a1 1 0 001.414 1.414l.707-.707zM18 10a1 1 0 01-1 1h-1a1 1 0 110-2h1a1 1 0 011 1zM5.05 6.464A1 1 0 106.464 5.05l-.707-.707a1 1 0 00-1.414 1.414l.707.707zM5 10a1 1 0 01-1 1H3a1 1 0 110-2h1a1 1 0 011 1zM8 16v-1h4v1a2 2 0 11-4 0zM12 14c.015-.34.208-.646.477-.859a4 4 0 10-4.954 0c.27.213.462.519.476.859h4.002z" />
          </svg>
          <span className="text-sm font-semibold text-gray-100">
            {briefingMutation.isPending ? 'Generating briefing...' : 'Generate Morning Briefing'}
          </span>
        </button>
      )}

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
          {weekly.data ? (
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
