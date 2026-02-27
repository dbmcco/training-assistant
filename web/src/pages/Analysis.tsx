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
  })

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Analysis</h1>
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
