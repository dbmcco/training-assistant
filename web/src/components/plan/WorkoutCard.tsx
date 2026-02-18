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
}

export default function WorkoutCard({ workout }: WorkoutCardProps) {
  const color = disciplineColors[workout.discipline] ?? 'text-gray-400'
  const bgColor = disciplineBgColors[workout.discipline] ?? 'bg-gray-400/10'
  const icon = disciplineIcons[workout.discipline] ?? '\u{1F3CB}'
  const statusStyle = statusStyles[workout.status] ?? statusStyles.upcoming

  const formatDuration = (minutes: number | null): string => {
    if (minutes == null) return ''
    if (minutes < 60) return `${minutes}m`
    const h = Math.floor(minutes / 60)
    const m = minutes % 60
    return m > 0 ? `${h}h ${m}m` : `${h}h`
  }

  return (
    <div
      className={`rounded-lg border border-gray-800 p-2.5 ${bgColor} transition-colors hover:border-gray-700`}
    >
      <div className="flex items-center gap-2 mb-1">
        <span className="text-sm">{icon}</span>
        <span className={`text-xs font-semibold uppercase tracking-wide ${color}`}>
          {workout.discipline}
        </span>
        <span className={`ml-auto text-[10px] font-medium px-1.5 py-0.5 rounded-full ${statusStyle}`}>
          {workout.status}
        </span>
      </div>
      <p className="text-sm text-gray-200 font-medium capitalize">
        {workout.workout_type.replace(/_/g, ' ')}
      </p>
      <div className="flex items-center gap-2 mt-1 text-xs text-gray-500">
        {workout.target_duration != null && (
          <span>{formatDuration(workout.target_duration)}</span>
        )}
        {workout.target_hr_zone != null && (
          <span className="uppercase">{workout.target_hr_zone.replace(/_/g, ' ')}</span>
        )}
      </div>
      {workout.description != null && (
        <p className="text-xs text-gray-500 mt-1 line-clamp-2">
          {workout.description}
        </p>
      )}
    </div>
  )
}
