import { useState } from 'react'
import type { Briefing } from '../../api/types'

interface BriefingBannerProps {
  briefing: Briefing
}

export default function BriefingBanner({ briefing }: BriefingBannerProps) {
  const [expanded, setExpanded] = useState(true)

  return (
    <div className="rounded-xl bg-gray-900 border border-gray-800 overflow-hidden">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex items-center justify-between w-full px-5 py-3 text-left hover:bg-gray-800/40 transition-colors"
      >
        <div className="flex items-center gap-2">
          <svg
            className="w-5 h-5 text-blue-400 shrink-0"
            viewBox="0 0 20 20"
            fill="currentColor"
          >
            <path d="M11 3a1 1 0 10-2 0v1a1 1 0 102 0V3zM15.657 5.757a1 1 0 00-1.414-1.414l-.707.707a1 1 0 001.414 1.414l.707-.707zM18 10a1 1 0 01-1 1h-1a1 1 0 110-2h1a1 1 0 011 1zM5.05 6.464A1 1 0 106.464 5.05l-.707-.707a1 1 0 00-1.414 1.414l.707.707zM5 10a1 1 0 01-1 1H3a1 1 0 110-2h1a1 1 0 011 1zM8 16v-1h4v1a2 2 0 11-4 0zM12 14c.015-.34.208-.646.477-.859a4 4 0 10-4.954 0c.27.213.462.519.476.859h4.002z" />
          </svg>
          <span className="text-sm font-semibold text-gray-100">
            Morning Briefing
          </span>
        </div>
        <svg
          className={`w-4 h-4 text-gray-400 transition-transform duration-200 ${
            expanded ? 'rotate-180' : ''
          }`}
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path
            fillRule="evenodd"
            d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      {expanded && (
        <div className="px-5 pb-4 text-sm text-gray-300 leading-relaxed">
          {briefing.content}
        </div>
      )}
    </div>
  )
}
