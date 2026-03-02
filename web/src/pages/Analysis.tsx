import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchDashboardTrends } from '../api/client'
import TrendsStatsPanel from '../components/dashboard/TrendsStatsPanel'

export default function Analysis() {
  const [trendMetric, setTrendMetric] = useState('readiness')
  const [trendDays, setTrendDays] = useState(180)

  const trendRange = useMemo(() => {
    const end = new Date()
    const start = new Date()
    start.setDate(end.getDate() - trendDays)
    const fmt = (d: Date) => d.toISOString().slice(0, 10)
    return { start: fmt(start), end: fmt(end) }
  }, [trendDays])

  const trends = useQuery({
    queryKey: ['dashboard', 'trends', trendMetric, trendRange.start, trendRange.end],
    queryFn: () => fetchDashboardTrends(trendRange.start, trendRange.end, trendMetric),
    staleTime: 5 * 60 * 1000,
    refetchInterval: 60 * 60 * 1000,
  })

  const executive = trends.data?.executive_summary
  const planWeek = trends.data?.plan_week
  const executiveStatusClasses =
    executive?.status_level === 'warning'
      ? 'border-red-500/40 bg-red-500/10 text-red-200'
      : executive?.status_level === 'watch'
        ? 'border-amber-500/40 bg-amber-500/10 text-amber-200'
        : 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200'

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Analysis</h1>
      </div>

      <div className="rounded-xl bg-gray-900 border border-gray-800 p-5 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-gray-300">Daily Executive Summary</h2>
            <p className="text-xs text-gray-500">
              {executive?.as_of ? `As of ${executive.as_of}` : 'Based on latest available daily data'}
            </p>
          </div>
          <div className={`rounded-full border px-3 py-1 text-xs font-medium ${executiveStatusClasses}`}>
            {executive?.status ?? 'Updating...'}
          </div>
        </div>

        <p className="text-sm text-gray-200">
          {executive?.summary ?? 'Building today’s executive view from your most recent trend data.'}
        </p>

        {planWeek && (
          <div className="rounded-lg border border-gray-800 bg-gray-950 px-3 py-2 text-xs text-gray-300">
            <div className="font-medium text-gray-200">
              Weekly Plan ({planWeek.start} to {planWeek.end})
            </div>
            <div className="mt-1 text-gray-400">
              {planWeek.on_plan_completed}/{planWeek.total_planned} on plan • {planWeek.remaining} remaining
            </div>
            {planWeek.next_sessions.length > 0 && (
              <ul className="mt-2 space-y-1 list-disc list-inside text-gray-300">
                {planWeek.next_sessions.map((session, idx) => (
                  <li key={`${session.date}-${idx}`}>
                    {session.date}: {session.label}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {executive?.recommendations && executive.recommendations.length > 0 && (
          <ul className="space-y-1 text-xs text-gray-300 list-disc list-inside">
            {executive.recommendations.map((recommendation, idx) => (
              <li key={`${idx}-${recommendation}`}>{recommendation}</li>
            ))}
          </ul>
        )}
      </div>

      <TrendsStatsPanel
        trends={trends.data}
        isLoading={trends.isLoading}
        isError={trends.isError}
        metric={trendMetric}
        onMetricChange={setTrendMetric}
        days={trendDays}
        onDaysChange={setTrendDays}
      />
    </div>
  )
}
