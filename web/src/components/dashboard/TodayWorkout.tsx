import { useMemo } from 'react'
import type { TodayWorkout as TodayWorkoutType } from '../../api/types'

interface TodayWorkoutProps {
  workout: TodayWorkoutType
}

function normalizePlannedDurationMinutes(rawDuration: number | null): number | null {
  if (rawDuration == null || rawDuration <= 0) return null
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

interface ParsedWorkout {
  summary: string
  steps: string[]
  cues: string[]
}

function parseDescription(description: string | null): ParsedWorkout {
  if (!description) return { summary: '', steps: [], cues: [] }

  const sections = description.split('\n\n')
  const summary = sections[0]?.trim() ?? ''
  const steps: string[] = []
  const cues: string[] = []

  for (const section of sections.slice(1)) {
    const lines = section.split('\n').map((l) => l.trim()).filter(Boolean)
    if (!lines.length) continue

    const header = lines[0].toLowerCase()
    if (header.includes('session plan') || header.includes('workout plan')) {
      for (const line of lines.slice(1)) {
        // Strip leading number + period (e.g., "1. ") but keep the rest
        const cleaned = line.replace(/^\d+\.\s*/, '')
        if (cleaned) steps.push(cleaned)
      }
    } else if (header.includes('coaching cue') || header.includes('notes')) {
      for (const line of lines.slice(1)) {
        const cleaned = line.replace(/^-\s*/, '')
        if (cleaned) cues.push(cleaned)
      }
    } else {
      // Unnumbered lines that look like steps (start with a number)
      for (const line of lines) {
        const match = line.match(/^\d+\.\s*(.+)/)
        if (match) {
          steps.push(match[1])
        } else if (line.startsWith('-')) {
          cues.push(line.replace(/^-\s*/, ''))
        }
      }
    }
  }

  return { summary, steps, cues }
}

function StepCard({ step, index }: { step: string; index: number }) {
  // Split on @ to separate the action from the pace/effort
  const atIndex = step.indexOf('@')
  let action: string
  let detail: string | null = null
  let parenthetical: string | null = null

  if (atIndex > 0) {
    action = step.slice(0, atIndex).trim()
    const rest = step.slice(atIndex + 1).trim()
    // Check for parenthetical cue at end
    const parenMatch = rest.match(/^(.+?)\s*\((.+)\)\s*$/)
    if (parenMatch) {
      detail = parenMatch[1].trim()
      parenthetical = parenMatch[2].trim()
    } else {
      detail = rest
    }
  } else {
    // Check for parenthetical without @
    const parenMatch = step.match(/^(.+?)\s*\((.+)\)\s*$/)
    if (parenMatch) {
      action = parenMatch[1].trim()
      parenthetical = parenMatch[2].trim()
    } else {
      action = step
    }
  }

  return (
    <div className="flex gap-3 items-start">
      <div className="shrink-0 w-6 h-6 rounded-full bg-blue-500/20 text-blue-400 text-xs font-bold flex items-center justify-center mt-0.5">
        {index + 1}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-gray-200 font-medium leading-snug">{action}</p>
        {detail && (
          <p className="text-xs text-blue-300/80 font-mono mt-0.5">{detail}</p>
        )}
        {parenthetical && (
          <p className="text-xs text-gray-500 mt-0.5 italic">{parenthetical}</p>
        )}
      </div>
    </div>
  )
}

function formatDistance(meters: number | null): string | null {
  if (meters == null || meters <= 0) return null
  const miles = meters / 1609.34
  return `${miles.toFixed(1)} mi`
}

export default function TodayWorkout({ workout }: TodayWorkoutProps) {
  const icon = disciplineIcons[workout.discipline] ?? '\u{1F3CB}'
  const statusClass = statusStyles[workout.status] ?? statusStyles.upcoming
  const durationMinutes = normalizePlannedDurationMinutes(workout.target_duration)
  const distanceLabel = formatDistance(workout.target_distance ?? null)
  const parsed = useMemo(() => parseDescription(workout.description), [workout.description])

  return (
    <div className="rounded-xl bg-gray-900 border border-gray-800 p-5">
      <h3 className="text-sm font-semibold text-gray-400 mb-3">
        Today&apos;s Workout
      </h3>

      {/* Header */}
      <div className="flex items-start gap-3 mb-4">
        <div className="text-2xl shrink-0" role="img" aria-label={workout.discipline}>
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-base font-semibold text-gray-100 capitalize">
              {(workout.workout_type ?? workout.type ?? workout.discipline).replace(/_/g, ' ')}
            </span>
            <span
              className={`px-2 py-0.5 rounded-full text-xs font-medium border ${statusClass}`}
            >
              {workout.status}
            </span>
          </div>
          <div className="flex items-center gap-3 mt-1 text-xs text-gray-500">
            {durationMinutes != null && <span>{durationMinutes} min</span>}
            {distanceLabel && <span>{distanceLabel}</span>}
          </div>
          {parsed.summary && (
            <p className="text-sm text-gray-400 mt-1.5 leading-relaxed">{parsed.summary}</p>
          )}
        </div>
      </div>

      {/* Steps */}
      {parsed.steps.length > 0 && (
        <div className="space-y-2.5 mb-4">
          {parsed.steps.map((step, i) => (
            <StepCard key={i} step={step} index={i} />
          ))}
        </div>
      )}

      {/* Coaching Cues */}
      {parsed.cues.length > 0 && (
        <div className="rounded-lg bg-gray-800/50 border border-gray-700/50 px-3 py-2.5">
          <p className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider mb-1.5">Coaching Cues</p>
          <ul className="space-y-1">
            {parsed.cues.map((cue, i) => (
              <li key={i} className="text-xs text-gray-400 leading-relaxed flex gap-1.5">
                <span className="text-gray-600 shrink-0">&bull;</span>
                <span>{cue}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Fallback: if no steps parsed, show raw description */}
      {parsed.steps.length === 0 && !parsed.summary && workout.description && (
        <p className="text-sm text-gray-400 leading-relaxed whitespace-pre-line">
          {workout.description}
        </p>
      )}
    </div>
  )
}
