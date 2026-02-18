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

interface WeeklyVolumeProps {
  volume: VolumeEntry[]
}

const disciplineColors: Record<string, string> = {
  run: '#3b82f6',
  bike: '#22c55e',
  swim: '#06b6d4',
  strength: '#a855f7',
}

export default function WeeklyVolume({ volume }: WeeklyVolumeProps) {
  const data = volume.map((v) => ({
    discipline: v.discipline.charAt(0).toUpperCase() + v.discipline.slice(1),
    duration: v.duration_minutes,
    distance: v.distance_km,
    fill: disciplineColors[v.discipline] ?? '#6b7280',
  }))

  return (
    <div className="rounded-xl bg-gray-900 border border-gray-800 p-5">
      <h3 className="text-sm font-semibold text-gray-400 mb-4">
        Weekly Volume
      </h3>

      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ left: 10, right: 10, top: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" horizontal={false} />
            <XAxis
              type="number"
              tick={{ fill: '#6b7280', fontSize: 12 }}
              axisLine={{ stroke: '#374151' }}
              tickLine={false}
              unit=" min"
            />
            <YAxis
              type="category"
              dataKey="discipline"
              tick={{ fill: '#9ca3af', fontSize: 12 }}
              axisLine={false}
              tickLine={false}
              width={70}
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
                const v = value as number
                const p = props as { payload: { distance: number } }
                return [`${v} min (${p.payload.distance} km)`, 'Volume']
              }}
            />
            <Bar dataKey="duration" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
