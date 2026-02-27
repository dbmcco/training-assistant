import {
  useMemo,
  useState,
} from 'react'
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts'
import type { VolumeEntry } from '../../api/types'
import {
  isSwimDiscipline,
  kilometersToMiles,
  kilometersToYards,
} from '../../utils/units'

interface WeeklyVolumeProps {
  volume: VolumeEntry[]
}

const disciplineColors: Record<string, string> = {
  run: '#3b82f6',
  bike: '#22c55e',
  swim: '#06b6d4',
  strength: '#a855f7',
  cross_training: '#f59e0b',
  walk: '#14b8a6',
  other: '#6b7280',
}

function formatDisciplineLabel(discipline: string): string {
  return discipline
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (match) => match.toUpperCase())
}

export default function WeeklyVolume({ volume }: WeeklyVolumeProps) {
  const [unit, setUnit] = useState<'minutes' | 'distance'>('minutes')
  const [disabledTypes, setDisabledTypes] = useState<Set<string>>(new Set())

  const disciplines = useMemo(
    () => Array.from(new Set(volume.map((v) => v.discipline))),
    [volume],
  )
  const hasAnyVolume = volume.length > 0

  const filtered = useMemo(
    () => volume.filter((v) => !disabledTypes.has(v.discipline)),
    [volume, disabledTypes],
  )

  const data = volume.map((v) => {
    const swim = isSwimDiscipline(v.discipline)
    return {
      discipline: formatDisciplineLabel(v.discipline),
      duration: v.duration_minutes,
      distance: swim
        ? Math.round(kilometersToYards(v.distance_km))
        : Number(kilometersToMiles(v.distance_km).toFixed(1)),
      distanceUnit: swim ? 'yd' : 'mi',
      distancePrecision: swim ? 0 : 1,
      count: v.count,
      fill: disciplineColors[v.discipline] ?? '#6b7280',
      key: v.discipline,
    }
  })

  const filteredData = data.filter((d) => !disabledTypes.has(d.key))

  const toggleType = (discipline: string) => {
    setDisabledTypes((prev) => {
      const next = new Set(prev)
      if (next.has(discipline)) {
        next.delete(discipline)
      } else {
        next.add(discipline)
      }
      return next
    })
  }

  const valueKey = unit === 'minutes' ? 'duration' : 'distance'
  const axisUnit = unit === 'minutes' ? ' min' : undefined

  return (
    <div className="rounded-xl bg-gray-900 border border-gray-800 p-5">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <h3 className="text-sm font-semibold text-gray-400">
          Weekly Volume
        </h3>
        <div className="inline-flex rounded-md border border-gray-700 overflow-hidden">
          <button
            onClick={() => setUnit('minutes')}
            className={`px-2.5 py-1 text-xs ${
              unit === 'minutes'
                ? 'bg-blue-500/20 text-blue-300'
                : 'bg-gray-950 text-gray-400 hover:text-gray-200'
            }`}
          >
            Minutes
          </button>
          <button
            onClick={() => setUnit('distance')}
            className={`px-2.5 py-1 text-xs ${
              unit === 'distance'
                ? 'bg-blue-500/20 text-blue-300'
                : 'bg-gray-950 text-gray-400 hover:text-gray-200'
            }`}
          >
            Distance
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5 mb-3">
        {disciplines.map((discipline) => {
          const enabled = !disabledTypes.has(discipline)
          return (
            <button
              key={discipline}
              onClick={() => toggleType(discipline)}
              className={`px-2 py-1 rounded-md text-[11px] border transition-colors ${
                enabled
                  ? 'border-gray-700 bg-gray-800 text-gray-200'
                  : 'border-gray-800 bg-gray-900 text-gray-500'
              }`}
            >
              {discipline.replace(/_/g, ' ')}
            </button>
          )
        })}
      </div>

      {hasAnyVolume ? (
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={filteredData} layout="vertical" margin={{ left: 10, right: 10, top: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" horizontal={false} />
              <XAxis
                type="number"
                tick={{ fill: '#6b7280', fontSize: 12 }}
                axisLine={{ stroke: '#374151' }}
                tickLine={false}
                unit={axisUnit}
              />
              <YAxis
                type="category"
                dataKey="discipline"
                tick={{ fill: '#9ca3af', fontSize: 12 }}
                axisLine={false}
                tickLine={false}
                width={96}
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
                formatter={(value: unknown, _name: unknown, props: unknown) => {
                  const v = Number(value as number)
                  const p = props as {
                    payload: {
                      distance: number
                      distanceUnit: string
                      distancePrecision: number
                      duration: number
                      count: number
                    }
                  }
                  const distanceText =
                    p.payload.distancePrecision === 0
                      ? `${Math.round(p.payload.distance).toLocaleString()} ${p.payload.distanceUnit}`
                      : `${p.payload.distance.toFixed(1)} ${p.payload.distanceUnit}`
                  if (unit === 'minutes') {
                    return [`${v} min (${distanceText}, ${p.payload.count} sessions)`, 'Volume']
                  }
                  const valueText =
                    p.payload.distancePrecision === 0
                      ? `${Math.round(v).toLocaleString()} ${p.payload.distanceUnit}`
                      : `${v.toFixed(1)} ${p.payload.distanceUnit}`
                  return [`${valueText} (${p.payload.duration} min, ${p.payload.count} sessions)`, 'Volume']
                }}
              />
              <Bar dataKey={valueKey} radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="h-48 rounded-lg border border-gray-800 bg-gray-950/40 flex items-center justify-center text-xs text-gray-500">
          No activity volume recorded yet this week.
        </div>
      )}

      {hasAnyVolume && filtered.length === 0 && (
        <div className="text-xs text-gray-500 mt-2">Enable at least one type.</div>
      )}
    </div>
  )
}
