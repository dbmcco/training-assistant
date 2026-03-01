import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceArea,
  ReferenceDot,
} from 'recharts'
import type { DashboardTrends } from '../../api/types'
import { formatDistanceFromKilometers } from '../../utils/units'

interface TrendsStatsPanelProps {
  trends: DashboardTrends | undefined
  isLoading: boolean
  isError: boolean
  metric: string
  onMetricChange: (metric: string) => void
  days: number
  onDaysChange: (days: number) => void
}

function fmt(value: number | null | undefined, unit: string): string {
  if (value == null) {
    return '--'
  }
  const numeric = Number(value)
  if (Number.isNaN(numeric)) {
    return '--'
  }
  const rounded = Number.isInteger(numeric) ? numeric.toString() : numeric.toFixed(2)
  if (!unit || unit === 'score' || unit === 'load') {
    return rounded
  }
  return `${rounded} ${unit}`
}

function fmtSigned(value: number | null | undefined, unit = ''): string {
  if (value == null || Number.isNaN(Number(value))) {
    return '--'
  }
  const numeric = Number(value)
  const abs = Math.abs(numeric)
  const core = Number.isInteger(abs) ? abs.toString() : abs.toFixed(2)
  const sign = numeric > 0 ? '+' : numeric < 0 ? '-' : ''
  return unit ? `${sign}${core} ${unit}` : `${sign}${core}`
}

interface TrendBand {
  lower: number
  upper: number
  label: string
}

interface TrendGuidance {
  level: 'good' | 'watch' | 'warning'
  title: string
  detail: string
  action: string
}

function shortDate(value: string): string {
  return new Date(value).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
  })
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function computeTargetBand(
  metric: string,
  summary: DashboardTrends['series_summary'] | undefined,
): TrendBand | null {
  const avg = summary?.avg ?? summary?.latest
  if (metric === 'readiness') return { lower: 65, upper: 85, label: 'Readiness target zone' }
  if (metric === 'sleep_score') return { lower: 72, upper: 100, label: 'Sleep target zone' }
  if (metric === 'body_battery') return { lower: 55, upper: 100, label: 'Body battery target zone' }
  if (metric === 'stress') return { lower: 0, upper: 40, label: 'Keep stress low' }

  if (metric === 'resting_hr' && avg != null) {
    return { lower: clamp(avg - 3, 30, 120), upper: clamp(avg + 3, 30, 120), label: 'Personal baseline' }
  }
  if ((metric === 'hrv_7d' || metric === 'hrv_night') && avg != null) {
    return { lower: Math.max(20, avg * 0.9), upper: avg * 1.1, label: 'HRV baseline band' }
  }
  if ((metric === 'load_7d' || metric === 'load_28d') && avg != null) {
    return { lower: Math.max(0, avg * 0.8), upper: avg * 1.2, label: 'Load band' }
  }
  if ((metric === 'vo2_run' || metric === 'vo2_bike' || metric === 'endurance') && avg != null) {
    return { lower: avg * 0.95, upper: avg * 1.05, label: 'Fitness baseline band' }
  }
  return null
}

function guidanceFromBandDistance(
  metric: string,
  latest: number,
  band: TrendBand | null,
): { level: 'good' | 'watch' | 'warning'; detail: string } {
  if (!band) {
    return {
      level: 'watch',
      detail: `Latest value ${fmt(latest, '')}. No target band available for this metric.`,
    }
  }

  if (latest >= band.lower && latest <= band.upper) {
    return {
      level: 'good',
      detail: `${fmt(latest, '')} is inside the ${fmt(band.lower, '')}-${fmt(band.upper, '')} band.`,
    }
  }

  const span = Math.max(1, band.upper - band.lower)
  const delta = latest < band.lower ? band.lower - latest : latest - band.upper
  const distancePct = delta / span

  const level = distancePct >= 0.35 ? 'warning' : 'watch'
  if (metric === 'stress' || metric === 'resting_hr') {
    return {
      level,
      detail: `${fmt(latest, '')} is higher than your preferred ${band.label.toLowerCase()}.`,
    }
  }
  return {
    level,
    detail: `${fmt(latest, '')} is outside the ${band.label.toLowerCase()} (${fmt(
      band.lower,
      '',
    )}-${fmt(band.upper, '')}).`,
  }
}

function buildTrendGuidance(
  metric: string,
  trends: DashboardTrends | undefined,
  band: TrendBand | null,
): TrendGuidance {
  const latest = trends?.series_summary?.latest
  const delta = trends?.series_summary?.delta
  const analysis = trends?.analysis

  if (latest == null) {
    return {
      level: 'watch',
      title: 'Not enough data yet',
      detail: 'No current value in this range.',
      action: 'Keep syncing device data and check this metric over a wider date range.',
    }
  }

  if (metric === 'load_7d' || metric === 'load_28d') {
    const acwr = analysis?.load_management?.acwr
    const acwrBand = analysis?.load_management?.acwr_band
    if (acwr != null && acwrBand) {
      if (acwrBand === 'balanced') {
        return {
          level: 'good',
          title: 'Load is in a healthy range',
          detail: `ACWR ${acwr} is balanced for current training.`,
          action: 'Maintain current rhythm and keep hard days separated by recovery.',
        }
      }
      if (acwrBand === 'overreaching_risk') {
        return {
          level: 'warning',
          title: 'Load is trending too high',
          detail: `ACWR ${acwr} signals overreaching risk.`,
          action: 'Reduce intensity for 1-2 sessions and prioritize sleep/recovery this week.',
        }
      }
      return {
        level: 'watch',
        title: 'Load may be too low',
        detail: `ACWR ${acwr} indicates underloading.`,
        action: 'Add one purposeful quality session if recovery markers stay stable.',
      }
    }
  }

  const bandAssessment = guidanceFromBandDistance(metric, latest, band)
  const direction =
    delta == null ? 'stable' : delta > 0 ? 'upward' : delta < 0 ? 'downward' : 'stable'

  if (bandAssessment.level === 'good') {
    return {
      level: 'good',
      title: 'Trend is on target',
      detail: `${bandAssessment.detail} Direction is ${direction}.`,
      action: 'Keep the current plan and monitor for consistent week-over-week stability.',
    }
  }
  if (bandAssessment.level === 'warning') {
    return {
      level: 'warning',
      title: 'Trend needs intervention',
      detail: `${bandAssessment.detail} Direction is ${direction}.`,
      action: 'Adjust this week’s sessions (volume or intensity) and re-check this metric in 48h.',
    }
  }
  return {
    level: 'watch',
    title: 'Trend needs attention',
    detail: `${bandAssessment.detail} Direction is ${direction}.`,
    action: 'Make a small adjustment and confirm the trend is back inside range over the next few days.',
  }
}

export default function TrendsStatsPanel({
  trends,
  isLoading,
  isError,
  metric,
  onMetricChange,
  days,
  onDaysChange,
}: TrendsStatsPanelProps) {
  const options = trends?.metric_options ?? []
  const chartData = (trends?.series ?? []).map((point) => ({
    ...point,
  }))
  const summary = trends?.series_summary
  const unit = trends?.metric_unit ?? ''
  const hasSeriesValues = (trends?.series ?? []).some((point) => point.value != null)
  const analysis = trends?.analysis
  const targetBand = computeTargetBand(metric, summary)
  const guidance = buildTrendGuidance(metric, trends, targetBand)
  const eventColorByLevel: Record<string, string> = {
    good: '#34d399',
    watch: '#fbbf24',
    warning: '#f87171',
  }

  const valueByDate = new Map(chartData.map((point) => [point.date, point.value]))
  const eventPoints = (trends?.events ?? [])
    .map((event) => ({
      ...event,
      value: valueByDate.get(event.date),
    }))
    .filter((event) => event.value != null) as Array<
    NonNullable<DashboardTrends['events']>[number] & { value: number }
  >

  return (
    <div className="rounded-xl bg-gray-900 border border-gray-800 p-5 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-gray-300">Trends & Stats</h3>
        <div className="flex items-center gap-2">
          <select
            value={metric}
            onChange={(e) => onMetricChange(e.target.value)}
            className="bg-gray-950 border border-gray-700 rounded-md px-2.5 py-1.5 text-xs text-gray-200"
          >
            {options.length > 0 ? (
              options.map((opt) => (
                <option key={opt.key} value={opt.key}>
                  {opt.label}
                </option>
              ))
            ) : (
              <option value={metric}>Metric</option>
            )}
          </select>
          <select
            value={days}
            onChange={(e) => onDaysChange(Number(e.target.value))}
            className="bg-gray-950 border border-gray-700 rounded-md px-2.5 py-1.5 text-xs text-gray-200"
          >
            <option value={30}>30d</option>
            <option value={60}>60d</option>
            <option value={90}>90d</option>
            <option value={180}>180d</option>
            <option value={365}>365d</option>
          </select>
        </div>
      </div>

      {trends?.range_adjusted && trends.latest_data_date && (
        <div className="rounded-lg bg-amber-500/10 border border-amber-500/30 px-3 py-2 text-xs text-amber-200">
          Showing latest available data window ending {trends.latest_data_date}.
        </div>
      )}

      {isError && (
        <div className="rounded-lg bg-red-500/10 border border-red-500/30 px-3 py-2 text-xs text-red-300">
          Could not load trend stats from the API.
        </div>
      )}

      {isLoading ? (
        <div className="h-52 rounded-lg bg-gray-950 border border-gray-800 animate-pulse" />
      ) : !hasSeriesValues ? (
        <div className="h-52 rounded-lg bg-gray-950 border border-gray-800 flex items-center justify-center text-xs text-gray-500">
          No metric values found for this range.
        </div>
      ) : (
        <div className="h-52">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ left: 0, right: 10, top: 5, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis
                dataKey="date"
                tickFormatter={(value) => shortDate(String(value))}
                tick={{ fill: '#6b7280', fontSize: 11 }}
                axisLine={{ stroke: '#374151' }}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: '#6b7280', fontSize: 11 }}
                axisLine={{ stroke: '#374151' }}
                tickLine={false}
                width={45}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#1f2937',
                  border: '1px solid #374151',
                  borderRadius: '0.5rem',
                  fontSize: '0.75rem',
                }}
                labelStyle={{ color: '#f3f4f6' }}
                itemStyle={{ color: '#d1d5db' }}
                labelFormatter={(value) => shortDate(String(value))}
                formatter={(value: unknown) => [fmt(value as number, unit), trends?.metric_label ?? 'Metric']}
              />
              {targetBand && (
                <ReferenceArea
                  y1={targetBand.lower}
                  y2={targetBand.upper}
                  fill="#22c55e"
                  fillOpacity={0.08}
                  strokeOpacity={0}
                />
              )}
              <Line
                type="monotone"
                dataKey="value"
                stroke="#60a5fa"
                strokeWidth={2}
                dot={false}
                name={trends?.metric_label ?? 'Metric'}
                connectNulls
              />
              {eventPoints.slice(-8).map((event, idx) => (
                <ReferenceDot
                  key={`${event.date}-${event.type}-${idx}`}
                  x={event.date}
                  y={event.value}
                  r={4}
                  ifOverflow="extendDomain"
                  fill={eventColorByLevel[event.level] ?? '#fbbf24'}
                  stroke="#111827"
                  strokeWidth={1.5}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <div
        className={`rounded-lg border px-3 py-3 ${
          guidance.level === 'warning'
            ? 'border-red-500/40 bg-red-500/10'
            : guidance.level === 'watch'
              ? 'border-amber-500/40 bg-amber-500/10'
              : 'border-emerald-500/40 bg-emerald-500/10'
        }`}
      >
        <div className="text-[11px] uppercase tracking-wide text-gray-300">Trend Guidance</div>
        <div className="mt-1 text-sm font-semibold text-gray-100">{guidance.title}</div>
        <div className="mt-1 text-xs text-gray-300">{guidance.detail}</div>
        {targetBand && (
          <div className="mt-1 text-[11px] text-gray-400">
            {targetBand.label}: {fmt(targetBand.lower, unit)} - {fmt(targetBand.upper, unit)}
          </div>
        )}
        <div className="mt-2 text-xs text-gray-200">
          <span className="text-gray-400">Next move:</span> {guidance.action}
        </div>
      </div>

      {trends?.coach_summary && (
        <div className="rounded-lg bg-gray-950 border border-gray-800 px-3 py-3">
          <div className="text-[11px] uppercase tracking-wide text-gray-500">AI Summary</div>
          <div className="mt-1 text-sm font-semibold text-gray-100">
            {trends.coach_summary.headline}
          </div>
          {trends.coach_summary.bullets.length > 0 && (
            <ul className="mt-2 space-y-1 text-xs text-gray-300 list-disc list-inside">
              {trends.coach_summary.bullets.map((bullet, idx) => (
                <li key={`${idx}-${bullet}`}>{bullet}</li>
              ))}
            </ul>
          )}
          <div className="mt-2 text-xs text-blue-200">
            <span className="text-blue-300">Recommendation:</span>{' '}
            {trends.coach_summary.recommended_action}
          </div>
        </div>
      )}

      {trends?.events && trends.events.length > 0 && (
        <div className="rounded-lg bg-gray-950 border border-gray-800 overflow-hidden">
          <div className="px-3 py-2 text-xs text-gray-400 border-b border-gray-800">
            Key Events In Range
          </div>
          <div className="max-h-44 overflow-y-auto divide-y divide-gray-800">
            {trends.events.slice(-8).map((event, idx) => (
              <div key={`${event.date}-${event.type}-${idx}`} className="px-3 py-2">
                <div className="flex items-center justify-between gap-2">
                  <div
                    className={`text-xs font-semibold ${
                      event.level === 'warning'
                        ? 'text-red-300'
                        : event.level === 'watch'
                          ? 'text-amber-300'
                          : 'text-emerald-300'
                    }`}
                  >
                    {event.title}
                  </div>
                  <div className="text-[11px] text-gray-500">{shortDate(event.date)}</div>
                </div>
                <div className="text-xs text-gray-400 mt-0.5">{event.detail}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
        <div className="rounded-lg bg-gray-950 border border-gray-800 px-3 py-2">
          <div className="text-[11px] text-gray-500">Latest</div>
          <div className="text-sm font-semibold text-gray-200">{fmt(summary?.latest ?? null, unit)}</div>
        </div>
        <div className="rounded-lg bg-gray-950 border border-gray-800 px-3 py-2">
          <div className="text-[11px] text-gray-500">Average</div>
          <div className="text-sm font-semibold text-gray-200">{fmt(summary?.avg ?? null, unit)}</div>
        </div>
        <div className="rounded-lg bg-gray-950 border border-gray-800 px-3 py-2">
          <div className="text-[11px] text-gray-500">Min / Max</div>
          <div className="text-sm font-semibold text-gray-200">
            {fmt(summary?.min ?? null, unit)} / {fmt(summary?.max ?? null, unit)}
          </div>
        </div>
        <div className="rounded-lg bg-gray-950 border border-gray-800 px-3 py-2">
          <div className="text-[11px] text-gray-500">Delta</div>
          <div className="text-sm font-semibold text-gray-200">{fmt(summary?.delta ?? null, unit)}</div>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
        <div className="rounded-lg bg-gray-950 border border-gray-800 px-3 py-2">
          <div className="text-[11px] text-gray-500">Activities</div>
          <div className="text-sm font-semibold text-gray-200">
            {trends ? trends.stats.total_activities : '--'}
          </div>
        </div>
        <div className="rounded-lg bg-gray-950 border border-gray-800 px-3 py-2">
          <div className="text-[11px] text-gray-500">Hours</div>
          <div className="text-sm font-semibold text-gray-200">{trends ? trends.stats.total_hours : '--'}</div>
        </div>
        <div className="rounded-lg bg-gray-950 border border-gray-800 px-3 py-2">
          <div className="text-[11px] text-gray-500">Distance</div>
          <div className="text-sm font-semibold text-gray-200">
            {trends ? formatDistanceFromKilometers(trends.stats.total_distance_km) : '--'}
          </div>
        </div>
        <div className="rounded-lg bg-gray-950 border border-gray-800 px-3 py-2">
          <div className="text-[11px] text-gray-500">Avg HR</div>
          <div className="text-sm font-semibold text-gray-200">{trends?.stats.avg_hr ?? '--'}</div>
        </div>
      </div>

      {analysis && (
        <div className="space-y-2">
          <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">
            Coach Analysis
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
            <div className="rounded-lg bg-gray-950 border border-gray-800 px-3 py-2">
              <div className="text-[11px] text-gray-500">Consistency</div>
              <div className="text-sm font-semibold text-gray-200">
                {analysis.consistency.consistency_pct}%
              </div>
              <div className="text-[11px] text-gray-500">
                {analysis.consistency.active_days}/{analysis.consistency.period_days} active days
              </div>
            </div>
            <div className="rounded-lg bg-gray-950 border border-gray-800 px-3 py-2">
              <div className="text-[11px] text-gray-500">Load Management</div>
              <div className="text-sm font-semibold text-gray-200">
                ACWR: {fmt(analysis.load_management.acwr, '')}
              </div>
              <div className="text-[11px] text-gray-500">
                Ramp: {fmtSigned(analysis.load_management.ramp_hours, 'h')} (
                {fmtSigned(analysis.load_management.ramp_pct, '%')})
              </div>
            </div>
            <div className="rounded-lg bg-gray-950 border border-gray-800 px-3 py-2">
              <div className="text-[11px] text-gray-500">Recovery Trend (7d vs prev 7d)</div>
              <div className="text-sm font-semibold text-gray-200">
                Ready {fmtSigned(analysis.recovery_trend.readiness_delta)}
              </div>
              <div className="text-[11px] text-gray-500">
                Sleep {fmtSigned(analysis.recovery_trend.sleep_delta)} | HRV{' '}
                {fmtSigned(analysis.recovery_trend.hrv_delta)}
              </div>
            </div>
            <div className="rounded-lg bg-gray-950 border border-gray-800 px-3 py-2">
              <div className="text-[11px] text-gray-500">Session Profile</div>
              <div className="text-sm font-semibold text-gray-200">
                {analysis.session_profile.hard_pct ?? '--'}% hard
              </div>
              <div className="text-[11px] text-gray-500">
                {analysis.session_profile.long_sessions} long sessions
              </div>
            </div>
            <div className="rounded-lg bg-gray-950 border border-gray-800 px-3 py-2">
              <div className="text-[11px] text-gray-500">Monotony / Strain</div>
              <div className="text-sm font-semibold text-gray-200">
                {fmt(analysis.consistency.monotony, '')} / {fmt(analysis.consistency.strain, '')}
              </div>
              <div className="text-[11px] text-gray-500">
                Avg daily {analysis.consistency.avg_daily_hours}h
              </div>
            </div>
            <div className="rounded-lg bg-gray-950 border border-gray-800 px-3 py-2">
              <div className="text-[11px] text-gray-500">Tri Balance</div>
              <div className="text-sm font-semibold text-gray-200">
                Run {analysis.discipline_balance.run?.pct ?? 0}% / Bike{' '}
                {analysis.discipline_balance.bike?.pct ?? 0}% / Swim{' '}
                {analysis.discipline_balance.swim?.pct ?? 0}%
              </div>
              <div className="text-[11px] text-gray-500">
                {analysis.discipline_balance.run?.hours ?? 0}h / {analysis.discipline_balance.bike?.hours ?? 0}h /{' '}
                {analysis.discipline_balance.swim?.hours ?? 0}h
              </div>
            </div>
          </div>
          {analysis.insights.length > 0 && (
            <div className="rounded-lg bg-gray-950 border border-gray-800 overflow-hidden">
              <div className="px-3 py-2 text-xs text-gray-400 border-b border-gray-800">
                Actionable Insights
              </div>
              <div className="divide-y divide-gray-800">
                {analysis.insights.map((insight, idx) => (
                  <div key={`${insight.title}-${idx}`} className="px-3 py-2">
                    <div
                      className={`text-xs font-semibold ${
                        insight.level === 'warning'
                          ? 'text-red-300'
                          : insight.level === 'watch'
                            ? 'text-amber-300'
                            : 'text-emerald-300'
                      }`}
                    >
                      {insight.title}
                    </div>
                    <div className="text-xs text-gray-400 mt-0.5">{insight.detail}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {trends?.activity_types && trends.activity_types.length > 0 && (
        <div className="rounded-lg bg-gray-950 border border-gray-800 overflow-hidden">
          <div className="px-3 py-2 text-xs text-gray-400 border-b border-gray-800">
            Activity Type Breakdown
          </div>
          <div className="max-h-44 overflow-y-auto">
            {trends.activity_types.map((item) => (
              <div
                key={`${item.activity_type}-${item.discipline}`}
                className="px-3 py-2 border-b last:border-b-0 border-gray-800 text-xs text-gray-300 flex items-center justify-between gap-2"
              >
                <div className="min-w-0">
                  <div className="truncate font-medium text-gray-200">{item.activity_type}</div>
                  <div className="text-gray-500">{item.discipline}</div>
                </div>
                <div className="text-right shrink-0">
                  <div>{item.count} sessions</div>
                  <div className="text-gray-500">
                    {item.hours}h / {formatDistanceFromKilometers(item.distance_km, item.discipline)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
