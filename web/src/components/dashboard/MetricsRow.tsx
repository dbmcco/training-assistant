import type { DashboardMetrics } from '../../api/types'

interface MetricsRowProps {
  metrics: DashboardMetrics
  trainingStatus: string | null
}

interface MetricItem {
  label: string
  value: string | number
  unit?: string
}

export default function MetricsRow({ metrics, trainingStatus }: MetricsRowProps) {
  const items: MetricItem[] = [
    {
      label: 'Sleep',
      value: metrics.sleep_score ?? '--',
    },
    {
      label: 'Body Battery',
      value: metrics.body_battery_wake ?? '--',
    },
    {
      label: 'HRV',
      value: metrics.hrv_last_night ?? '--',
      unit: 'ms',
    },
    {
      label: 'Training Status',
      value: trainingStatus ?? '--',
    },
  ]

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {items.map((item) => (
        <div
          key={item.label}
          className="rounded-xl bg-gray-900 border border-gray-800 px-4 py-3"
        >
          <p className="text-xs text-gray-500 mb-1">{item.label}</p>
          <p className="text-lg font-semibold text-gray-100">
            {item.value}
            {item.unit && (
              <span className="text-xs text-gray-500 ml-1">{item.unit}</span>
            )}
          </p>
        </div>
      ))}
    </div>
  )
}
