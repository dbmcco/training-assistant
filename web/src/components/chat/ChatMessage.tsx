interface ToolCallInfo {
  name: string
  status: 'calling' | 'done'
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  toolCalls?: ToolCallInfo[]
}

function ToolCallIndicator({ tool }: { tool: ToolCallInfo }) {
  const labels: Record<string, string> = {
    get_readiness: 'Checking your readiness...',
    get_schedule: 'Looking at your schedule...',
    get_metrics: 'Pulling your metrics...',
    get_races: 'Checking your races...',
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

export default function ChatMessage({ message }: { message: Message }) {
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
        <div className="whitespace-pre-wrap">{message.content}</div>
      </div>
    </div>
  )
}
