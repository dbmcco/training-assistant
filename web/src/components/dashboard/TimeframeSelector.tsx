interface TimeframeSelectorProps {
  days: number
  onChange: (days: number) => void
}

const options = [
  { label: '7d', value: 7 },
  { label: '14d', value: 14 },
  { label: '30d', value: 30 },
  { label: '90d', value: 90 },
]

export default function TimeframeSelector({ days, onChange }: TimeframeSelectorProps) {
  return (
    <div className="flex items-center gap-1">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            days === opt.value
              ? 'bg-blue-500/20 text-blue-300 border border-blue-500/30'
              : 'bg-gray-900 text-gray-500 border border-gray-800 hover:text-gray-300'
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}
