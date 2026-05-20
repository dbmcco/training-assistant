import type {
  ReviewWindowForward,
  ReviewWindowRetrospective,
  ReviewWindows,
} from '../../api/types'

interface ReviewWindowsPanelProps {
  review: ReviewWindows | null | undefined
  isLoading: boolean
  isError: boolean
}

function dateRangeLabel(start: string, end: string): string {
  const fmt = (value: string) =>
    new Date(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  return `${fmt(start)} - ${fmt(end)}`
}

function adherenceColor(adherencePct: number): string {
  if (adherencePct >= 80) return 'text-emerald-300'
  if (adherencePct >= 60) return 'text-amber-300'
  return 'text-red-300'
}

function RetrospectiveCard({
  title,
  window,
}: {
  title: string
  window: ReviewWindowRetrospective
}) {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/70 p-4 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-gray-200">{title}</h3>
        <span className="text-[11px] text-gray-400">{dateRangeLabel(window.start, window.end)}</span>
      </div>
      <div className="grid grid-cols-2 gap-3 text-xs">
        <div className="rounded-lg border border-gray-800 bg-gray-950 p-2">
          <div className="text-gray-500">Completed</div>
          <div className="mt-1 text-sm font-semibold text-gray-100">
            {window.sessions_completed} sessions
          </div>
          <div className="text-gray-400">{window.hours_completed} h</div>
        </div>
        <div className="rounded-lg border border-gray-800 bg-gray-950 p-2">
          <div className="text-gray-500">On plan</div>
          <div className={`mt-1 text-sm font-semibold ${adherenceColor(window.adherence_pct)}`}>
            {window.on_plan}/{window.planned_due}
          </div>
          <div className="text-gray-400">{Math.round(window.adherence_pct)}% adherence</div>
        </div>
      </div>
      <div className="text-xs text-gray-400">
        Active days: <span className="text-gray-200 font-medium">{window.active_days}</span>
        {' • '}
        Shifted matches: <span className="text-gray-200 font-medium">{window.shifted_substitutions}</span>
      </div>
      <p className="text-xs text-gray-300 leading-relaxed">{window.headline}</p>
    </div>
  )
}

function ForwardCard({ window }: { window: ReviewWindowForward }) {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/70 p-4 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-gray-200">Next 7 Days</h3>
        <span className="text-[11px] text-gray-400">{dateRangeLabel(window.start, window.end)}</span>
      </div>

      <div className="grid grid-cols-2 gap-3 text-xs">
        <div className="rounded-lg border border-gray-800 bg-gray-950 p-2">
          <div className="text-gray-500">Planned sessions</div>
          <div className="mt-1 text-sm font-semibold text-gray-100">{window.planned_sessions}</div>
        </div>
        <div className="rounded-lg border border-gray-800 bg-gray-950 p-2">
          <div className="text-gray-500">Planned hours</div>
          <div className="mt-1 text-sm font-semibold text-gray-100">{window.planned_hours} h</div>
        </div>
      </div>

      {window.disciplines.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {window.disciplines.map((item) => (
            <span
              key={item.discipline}
              className="inline-flex items-center gap-1 rounded-full border border-gray-700 bg-gray-950 px-2 py-1 text-[11px] text-gray-300"
            >
              <span className="font-medium text-gray-200">{item.discipline}</span>
              <span>{item.count}x</span>
              <span>{item.hours}h</span>
            </span>
          ))}
        </div>
      )}

      {window.key_sessions.length > 0 ? (
        <ul className="space-y-1 text-xs text-gray-300 list-disc list-inside">
          {window.key_sessions.slice(0, 5).map((session, idx) => (
            <li key={`${session.date}-${idx}`}>
              {session.date}: {session.label}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-gray-400">No upcoming sessions in the next 7 days yet.</p>
      )}
    </div>
  )
}

export default function ReviewWindowsPanel({
  review,
  isLoading,
  isError,
}: ReviewWindowsPanelProps) {
  if (isError) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
        Could not load retrospective/forward review.
      </div>
    )
  }

  if (isLoading || !review) {
    return (
      <div className="grid gap-4 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, idx) => (
          <div
            key={idx}
            className="rounded-xl border border-gray-800 bg-gray-900/70 p-4 h-48 animate-pulse"
          />
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div>
        <h2 className="text-sm font-semibold text-gray-300">Retrospective and Forward View</h2>
        <p className="text-xs text-gray-500">
          Rolling check on recent execution plus what is coming next.
        </p>
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <RetrospectiveCard title="Rolling 5 Days" window={review.rolling_5d} />
        <RetrospectiveCard title="Week to Date" window={review.week_to_date} />
        <ForwardCard window={review.forward_7d} />
      </div>
    </div>
  )
}
