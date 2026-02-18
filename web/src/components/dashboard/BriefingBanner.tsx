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
        <div className="px-5 pb-4 space-y-3">
          <p className="text-sm text-gray-300 leading-relaxed">
            {briefing.content}
          </p>

          {briefing.readiness_summary && (
            <div className="flex items-start gap-2 text-sm">
              <span className="shrink-0 text-green-400 font-medium">Readiness:</span>
              <span className="text-gray-400">{briefing.readiness_summary}</span>
            </div>
          )}

          {briefing.workout_recommendation && (
            <div className="flex items-start gap-2 text-sm">
              <span className="shrink-0 text-blue-400 font-medium">Workout:</span>
              <span className="text-gray-400">{briefing.workout_recommendation}</span>
            </div>
          )}

          {briefing.alerts && briefing.alerts.length > 0 && (
            <div className="flex flex-wrap gap-2 pt-1">
              {briefing.alerts.map((alert, i) => (
                <span
                  key={i}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-amber-500/10 text-xs text-amber-400 border border-amber-500/20"
                >
                  <svg className="w-3 h-3 shrink-0" viewBox="0 0 20 20" fill="currentColor">
                    <path
                      fillRule="evenodd"
                      d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                      clipRule="evenodd"
                    />
                  </svg>
                  {alert}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
