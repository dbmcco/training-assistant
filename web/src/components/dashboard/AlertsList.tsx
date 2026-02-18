interface AlertsListProps {
  alerts: string[]
}

export default function AlertsList({ alerts }: AlertsListProps) {
  if (alerts.length === 0) return null

  return (
    <div className="rounded-xl bg-gray-900 border border-gray-800 p-5">
      <h3 className="text-sm font-semibold text-gray-400 mb-3">Alerts</h3>

      <div className="space-y-2">
        {alerts.map((alert, index) => (
          <div
            key={index}
            className="flex items-start gap-2 text-sm"
          >
            <svg
              className="w-4 h-4 text-amber-400 shrink-0 mt-0.5"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path
                fillRule="evenodd"
                d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                clipRule="evenodd"
              />
            </svg>
            <span className="text-gray-300">{alert}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
