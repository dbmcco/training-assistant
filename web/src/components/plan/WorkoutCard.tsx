import type { PlannedWorkout } from '../../api/types'

const disciplineColors: Record<string, string> = {
  run: 'text-blue-400',
  bike: 'text-green-400',
  cycling: 'text-green-400',
  swim: 'text-cyan-400',
  strength: 'text-amber-400',
}

const disciplineBgColors: Record<string, string> = {
  run: 'bg-blue-400/10',
  bike: 'bg-green-400/10',
  cycling: 'bg-green-400/10',
  swim: 'bg-cyan-400/10',
  strength: 'bg-amber-400/10',
}

const disciplineIcons: Record<string, string> = {
  run: '\u{1F3C3}',
  bike: '\u{1F6B4}',
  cycling: '\u{1F6B4}',
  swim: '\u{1F3CA}',
  strength: '\u{1F4AA}',
}

const statusStyles: Record<string, string> = {
  completed: 'bg-green-500/20 text-green-400',
  missed: 'bg-red-500/20 text-red-400',
  upcoming: 'bg-gray-500/20 text-gray-400',
  skipped: 'bg-yellow-500/20 text-yellow-400',
}

interface WorkoutCardProps {
  workout: PlannedWorkout
  onClick?: (workout: PlannedWorkout) => void
}

function normalizeDiscipline(value: string | null | undefined): string {
  const raw = (value ?? '').trim().toLowerCase()
  if (!raw) return 'other'
  if (raw.startsWith('run') || raw.includes('trail')) return 'run'
  if (raw.startsWith('swim') || raw.includes('pool') || raw.includes('open_water'))
    return 'swim'
  if (
    raw.startsWith('bike') ||
    raw.startsWith('cycl') ||
    raw.includes('peloton') ||
    raw.includes('spin')
  ) {
    return 'bike'
  }
  if (raw.startsWith('strength') || raw.includes('lift')) return 'strength'
  return raw
}

function normalizePlannedDurationMinutes(rawDuration: number | null): number | null {
  if (rawDuration == null || rawDuration <= 0) return null
  // Garmin planned workouts arrive in seconds; user-entered edits may already be minutes.
  return rawDuration >= 600 ? Math.round(rawDuration / 60) : rawDuration
}

export default function WorkoutCard({ workout, onClick }: WorkoutCardProps) {
  const discipline = normalizeDiscipline(workout.discipline)
  const color = disciplineColors[discipline] ?? 'text-gray-400'
  const bgColor = disciplineBgColors[discipline] ?? 'bg-gray-400/10'
  const icon = disciplineIcons[discipline] ?? '\u{1F3CB}'
  const statusStyle = statusStyles[workout.status] ?? statusStyles.upcoming
  const interactive = typeof onClick === 'function'
  const durationMinutes = normalizePlannedDurationMinutes(workout.target_duration)

  const formatDuration = (minutes: number | null): string => {
    if (minutes == null) return ''
    if (minutes < 60) return `${minutes}m`
    const h = Math.floor(minutes / 60)
    const m = minutes % 60
    return m > 0 ? `${h}h ${m}m` : `${h}h`
  }

  const cardContent = (
    <>
      <div className="flex items-center gap-1.5 mb-1 min-w-0">
        <span className="text-xs shrink-0">{icon}</span>
        <span className={`text-[10px] font-semibold uppercase tracking-wide truncate min-w-0 ${color}`}>
          {workout.discipline}
        </span>
        <span className={`ml-auto shrink-0 text-[9px] font-medium px-1.5 py-0.5 rounded-full ${statusStyle}`}>
          {workout.status}
        </span>
      </div>
      <p className="text-sm text-gray-200 font-medium capitalize leading-tight break-words line-clamp-2">
        {(workout.workout_type || 'Workout').replace(/_/g, ' ')}
      </p>
      <div className="flex flex-wrap items-center gap-1.5 mt-1 text-[11px] text-gray-500">
        {durationMinutes != null && (
          <span>{formatDuration(durationMinutes)}</span>
        )}
        {workout.target_hr_zone != null && (
          <span className="uppercase">{workout.target_hr_zone.replace(/_/g, ' ')}</span>
        )}
      </div>
      {workout.description != null && (
        <p className="text-[11px] text-gray-500 mt-1 break-words line-clamp-2">
          {workout.description}
        </p>
      )}
    </>
  )

  if (interactive) {
    return (
      <button
        type="button"
        onClick={() => onClick(workout)}
        className={`w-full appearance-none text-left rounded-lg border border-gray-800 p-2 ${bgColor} transition-colors hover:border-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500/70 overflow-hidden cursor-pointer`}
        aria-label={`View details for ${workout.workout_type || 'workout'} on ${workout.date}`}
      >
        {cardContent}
      </button>
    )
  }

  return (
    <div
      className={`rounded-lg border border-gray-800 p-2 ${bgColor} transition-colors hover:border-gray-700 overflow-hidden`}
    >
      {cardContent}
    </div>
  )
}
