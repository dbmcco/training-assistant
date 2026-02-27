import MarkdownMessage from './MarkdownMessage'
import type {
  RecommendationChange,
  RecommendationDecision,
} from '../../api/types'

interface ToolCallInfo {
  name: string
  status: 'calling' | 'done'
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  toolCalls?: ToolCallInfo[]
  recommendationChange?: RecommendationChange | null
}

interface ChatMessageProps {
  message: Message
  decisionBusyId?: string | null
  onRecommendationDecision?: (
    recommendationId: string,
    decision: RecommendationDecision,
    note?: string,
    requestedChanges?: string,
  ) => void
}

function ToolCallIndicator({ tool }: { tool: ToolCallInfo }) {
  const labels: Record<string, string> = {
    get_readiness_score: 'Checking your readiness...',
    get_upcoming_workouts: 'Looking at your schedule...',
    get_daily_metrics: 'Pulling your metrics...',
    get_race_countdown: 'Checking your races...',
  }

  const label = labels[tool.name] ?? `Running ${tool.name}...`

  return (
    <div className="flex items-center gap-2 text-xs text-gray-400 py-1">
      {tool.status === 'calling' ? (
        <span className="inline-block w-3 h-3 border-2 border-gray-500 border-t-blue-400 rounded-full animate-spin" />
      ) : (
        <svg className="w-3 h-3 text-green-400" viewBox="0 0 20 20" fill="currentColor">
          <path
            fillRule="evenodd"
            d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
            clipRule="evenodd"
          />
        </svg>
      )}
      <span>{tool.status === 'done' ? label.replace('...', '') : label}</span>
    </div>
  )
}

function RecommendationActions({
  recommendation,
  decisionBusyId,
  onRecommendationDecision,
}: {
  recommendation: RecommendationChange
  decisionBusyId?: string | null
  onRecommendationDecision?: ChatMessageProps['onRecommendationDecision']
}) {
  if (!onRecommendationDecision) {
    return null
  }

  const isBusy = decisionBusyId === recommendation.id
  const isPending = recommendation.status === 'pending'

  if (!isPending) {
    const statusLabel = recommendation.status.replace('_', ' ')
    return (
      <div className="mt-3 rounded-lg border border-gray-700/80 bg-gray-900/60 px-3 py-2 text-xs text-gray-300">
        Recommendation {statusLabel}. Garmin sync: {recommendation.garmin_sync_status ?? 'n/a'}.
      </div>
    )
  }

  return (
    <div className="mt-3 rounded-lg border border-gray-700/80 bg-gray-900/60 px-3 py-3">
      <div className="text-xs text-gray-300 mb-2">Recommendation change</div>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={isBusy}
          onClick={() => onRecommendationDecision(recommendation.id, 'approved')}
          className="px-2.5 py-1.5 rounded-md text-xs font-medium bg-green-500/15 text-green-300 border border-green-500/30 hover:bg-green-500/25 disabled:opacity-60"
        >
          Approve
        </button>
        <button
          type="button"
          disabled={isBusy}
          onClick={() => onRecommendationDecision(recommendation.id, 'rejected')}
          className="px-2.5 py-1.5 rounded-md text-xs font-medium bg-red-500/15 text-red-300 border border-red-500/30 hover:bg-red-500/25 disabled:opacity-60"
        >
          Reject
        </button>
        <button
          type="button"
          disabled={isBusy}
          onClick={() => {
            const requested = window.prompt('What should change in this recommendation?')
            if (requested === null) return
            const trimmed = requested.trim()
            onRecommendationDecision(
              recommendation.id,
              'changes_requested',
              trimmed || undefined,
              trimmed || undefined,
            )
          }}
          className="px-2.5 py-1.5 rounded-md text-xs font-medium bg-amber-500/15 text-amber-300 border border-amber-500/30 hover:bg-amber-500/25 disabled:opacity-60"
        >
          Ask for changes
        </button>
      </div>
    </div>
  )
}

export default function ChatMessage({
  message,
  decisionBusyId,
  onRecommendationDecision,
}: ChatMessageProps) {
  const isUser = message.role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-3`}>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
          isUser
            ? 'bg-blue-600 text-white rounded-br-md'
            : 'bg-gray-800 text-gray-100 rounded-bl-md'
        }`}
      >
        {message.toolCalls && message.toolCalls.length > 0 && (
          <div className="mb-2 border-b border-gray-700 pb-2">
            {message.toolCalls.map((tool, i) => (
              <ToolCallIndicator key={`${tool.name}-${i}`} tool={tool} />
            ))}
          </div>
        )}
        {isUser ? (
          <div className="whitespace-pre-wrap">{message.content}</div>
        ) : (
          <>
            <MarkdownMessage content={message.content} />
            {message.recommendationChange && (
              <RecommendationActions
                recommendation={message.recommendationChange}
                decisionBusyId={decisionBusyId}
                onRecommendationDecision={onRecommendationDecision}
              />
            )}
          </>
        )}
      </div>
    </div>
  )
}
