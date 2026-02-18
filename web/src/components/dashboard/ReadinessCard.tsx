import type { Readiness } from '../../api/types'

interface ReadinessCardProps {
  readiness: Readiness
}

function scoreColor(score: number): string {
  if (score >= 70) return '#22c55e' // green-500
  if (score >= 40) return '#eab308' // yellow-500
  return '#ef4444' // red-500
}

function scoreTextClass(score: number): string {
  if (score >= 70) return 'text-green-400'
  if (score >= 40) return 'text-yellow-400'
  return 'text-red-400'
}

export default function ReadinessCard({ readiness }: ReadinessCardProps) {
  const { score, label, components } = readiness
  const color = scoreColor(score)

  // SVG circle gauge parameters
  const size = 140
  const strokeWidth = 10
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (score / 100) * circumference

  return (
    <div className="rounded-xl bg-gray-900 border border-gray-800 p-5">
      <h3 className="text-sm font-semibold text-gray-400 mb-4">Readiness</h3>

      <div className="flex flex-col items-center">
        <svg
          width={size}
          height={size}
          className="transform -rotate-90"
        >
          {/* Background circle */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            stroke="#1f2937"
            strokeWidth={strokeWidth}
            fill="none"
          />
          {/* Score arc */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            stroke={color}
            strokeWidth={strokeWidth}
            fill="none"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            className="transition-all duration-700 ease-out"
          />
        </svg>

        {/* Score text overlaid in center */}
        <div className="flex flex-col items-center -mt-[96px] mb-4">
          <span className={`text-3xl font-bold ${scoreTextClass(score)}`}>
            {score}
          </span>
          <span className="text-xs text-gray-400 mt-0.5">{label}</span>
        </div>
      </div>

      {/* Component breakdown */}
      {components.length > 0 && (
        <div className="mt-3 space-y-2">
          {components.map((c) => (
            <div key={c.name} className="flex items-center justify-between text-xs">
              <span className="text-gray-400">{c.name}</span>
              <div className="flex items-center gap-2">
                <div className="w-16 h-1.5 rounded-full bg-gray-800 overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${c.normalized}%`,
                      backgroundColor: scoreColor(c.normalized),
                    }}
                  />
                </div>
                <span className="text-gray-300 w-6 text-right">
                  {Math.round(c.normalized)}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
