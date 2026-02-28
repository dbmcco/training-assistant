import type { Adherence } from '../../api/types'

interface AdherenceBarProps {
  adherence: Adherence | undefined
  isLoading: boolean
}

export default function AdherenceBar({ adherence, isLoading }: AdherenceBarProps) {
  if (isLoading) {
    return (
      <div className="rounded-xl bg-gray-900 border border-gray-800 p-4 animate-pulse">
        <div className="h-4 bg-gray-800 rounded w-32 mb-3" />
        <div className="h-3 bg-gray-800 rounded-full" />
      </div>
    )
  }

  if (!adherence) return null

  const pct = Math.round(adherence.rate * 100)
  const strictPct =
    adherence.strict_rate != null ? Math.round(adherence.strict_rate * 100) : null
  const barColor =
    pct >= 80
      ? 'bg-green-500'
      : pct >= 60
        ? 'bg-yellow-500'
        : 'bg-red-500'

  return (
    <div className="rounded-xl bg-gray-900 border border-gray-800 p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-gray-300">Plan Adherence</h3>
        <span className="text-sm font-bold text-gray-100">{pct}% on plan</span>
      </div>
      <div className="w-full h-2.5 bg-gray-800 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
        <span>
          <span className="text-green-400 font-medium">{adherence.completed}</span> on plan
        </span>
        <span>
          <span className="text-emerald-400 font-medium">
            {adherence.aligned_substitutions ?? 0}
          </span>{' '}
          substitutions
        </span>
        <span>
          <span className="text-gray-300 font-medium">
            {adherence.strict_completed ?? adherence.completed}
          </span>{' '}
          strict
        </span>
        <span>
          <span className="text-red-400 font-medium">{adherence.missed}</span> missed
        </span>
        <span>
          <span className="text-gray-400 font-medium">
            {adherence.due_total ?? adherence.total}
          </span>{' '}
          due
        </span>
      </div>
      {strictPct != null && strictPct !== pct && (
        <div className="mt-2 text-[11px] text-gray-500">
          Strict completion without substitutions: {strictPct}%
        </div>
      )}
    </div>
  )
}
