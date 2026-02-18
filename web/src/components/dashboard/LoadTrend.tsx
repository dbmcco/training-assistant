import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts'
import type { LoadTrendEntry } from '../../api/types'

interface LoadTrendProps {
  loadTrend: LoadTrendEntry[]
}

export default function LoadTrend({ loadTrend }: LoadTrendProps) {
  const data = loadTrend.map((entry) => ({
    ...entry,
    label: new Date(entry.week_start).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
    }),
  }))

  return (
    <div className="rounded-xl bg-gray-900 border border-gray-800 p-5">
      <h3 className="text-sm font-semibold text-gray-400 mb-4">Load Trend</h3>

      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ left: 0, right: 10, top: 5, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis
              dataKey="label"
              tick={{ fill: '#6b7280', fontSize: 11 }}
              axisLine={{ stroke: '#374151' }}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: '#6b7280', fontSize: 11 }}
              axisLine={{ stroke: '#374151' }}
              tickLine={false}
              width={40}
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
            />
            <Line
              type="monotone"
              dataKey="acute"
              stroke="#ef4444"
              strokeWidth={2}
              dot={false}
              name="Acute"
            />
            <Line
              type="monotone"
              dataKey="chronic"
              stroke="#3b82f6"
              strokeWidth={2}
              dot={false}
              name="Chronic"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="flex items-center justify-center gap-4 mt-3">
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-0.5 rounded-full bg-red-500" />
          <span className="text-xs text-gray-500">Acute</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-0.5 rounded-full bg-blue-500" />
          <span className="text-xs text-gray-500">Chronic</span>
        </div>
      </div>
    </div>
  )
}
