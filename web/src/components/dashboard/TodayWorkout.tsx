import type { TodayWorkout as TodayWorkoutType } from '../../api/types'

interface TodayWorkoutProps {
  workout: TodayWorkoutType
}

function normalizePlannedDurationMinutes(rawDuration: number | null): number | null {
  if (rawDuration == null || rawDuration <= 0) return null
  // Garmin planned workouts arrive in seconds; user-entered edits may already be minutes.
  return rawDuration >= 600 ? Math.round(rawDuration / 60) : rawDuration
}

const disciplineIcons: Record<string, string> = {
  run: '\u{1F3C3}',
  bike: '\u{1F6B4}',
  swim: '\u{1F3CA}',
  strength: '\u{1F4AA}',
}

const statusStyles: Record<string, string> = {
  upcoming: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
  completed: 'bg-green-500/10 text-green-400 border-green-500/20',
  missed: 'bg-red-500/10 text-red-400 border-red-500/20',
  skipped: 'bg-gray-500/10 text-gray-400 border-gray-500/20',
}

export default function TodayWorkout({ workout }: TodayWorkoutProps) {
  const icon = disciplineIcons[workout.discipline] ?? '\u{1F3CB}'
  const statusClass = statusStyles[workout.status] ?? statusStyles.upcoming
  const durationMinutes = normalizePlannedDurationMinutes(workout.target_duration)

  return (
    <div className="rounded-xl bg-gray-900 border border-gray-800 p-5">
      <h3 className="text-sm font-semibold text-gray-400 mb-3">
        Today&apos;s Workout
      </h3>

      <div className="flex items-start gap-4">
        <div className="text-3xl shrink-0" role="img" aria-label={workout.discipline}>
          {icon}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-semibold text-gray-100 capitalize">
              {workout.type} {workout.discipline}
            </span>
            {durationMinutes != null && (
              <span className="text-xs text-gray-500">
                {durationMinutes} min
              </span>
            )}
          </div>

          {workout.description && (
            <p className="text-sm text-gray-400 leading-relaxed">
              {workout.description}
            </p>
          )}

          <span
            className={`inline-block mt-2 px-2 py-0.5 rounded-full text-xs font-medium border ${statusClass}`}
          >
            {workout.status}
          </span>
        </div>
      </div>
    </div>
  )
}
