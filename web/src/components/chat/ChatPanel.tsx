import { useState, useRef, useEffect, useCallback } from 'react'
import { useLocation } from 'react-router-dom'
import { streamChat } from '../../api/client'
import ChatMessage from './ChatMessage'
import ChatInput from './ChatInput'
import type { Message } from './ChatMessage'

interface ChatPanelProps {
  isOpen: boolean
  onToggle: () => void
}

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

function routeLabel(pathname: string): string {
  switch (pathname) {
    case '/':
      return 'dashboard'
    case '/plan':
      return 'plan'
    case '/races':
      return 'races'
    case '/profile':
      return 'profile'
    default:
      return 'unknown'
  }
}

export default function ChatPanel({ isOpen, onToggle }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [conversationId, setConversationId] = useState<string | undefined>()
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const location = useLocation()

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  async function handleSend(content: string) {
    const userMessage: Message = {
      id: generateId(),
      role: 'user',
      content,
    }

    const assistantMessage: Message = {
      id: generateId(),
      role: 'assistant',
      content: '',
      toolCalls: [],
    }

    setMessages((prev) => [...prev, userMessage, assistantMessage])
    setIsStreaming(true)

    try {
      const viewContext = {
        current_view: routeLabel(location.pathname),
        route: location.pathname,
      }

      const stream = streamChat(content, conversationId, viewContext)

      for await (const event of stream) {
        const eventType = event.event ?? (event.data as Record<string, unknown>)?.type
        const data = event.data ?? event

        switch (eventType) {
          case 'token': {
            const token = (data as Record<string, unknown>).token as string
            setMessages((prev) => {
              const updated = [...prev]
              const last = updated[updated.length - 1]
              if (last && last.role === 'assistant') {
                updated[updated.length - 1] = {
                  ...last,
                  content: last.content + token,
                }
              }
              return updated
            })
            break
          }

          case 'tool_call': {
            const toolName = (data as Record<string, unknown>).name as string
            setMessages((prev) => {
              const updated = [...prev]
              const last = updated[updated.length - 1]
              if (last && last.role === 'assistant') {
                updated[updated.length - 1] = {
                  ...last,
                  toolCalls: [
                    ...(last.toolCalls ?? []),
                    { name: toolName, status: 'calling' as const },
                  ],
                }
              }
              return updated
            })
            break
          }

          case 'tool_result': {
            const toolName = (data as Record<string, unknown>).name as string
            setMessages((prev) => {
              const updated = [...prev]
              const last = updated[updated.length - 1]
              if (last && last.role === 'assistant') {
                const toolCalls = (last.toolCalls ?? []).map((tc) =>
                  tc.name === toolName && tc.status === 'calling'
                    ? { ...tc, status: 'done' as const }
                    : tc,
                )
                updated[updated.length - 1] = { ...last, toolCalls }
              }
              return updated
            })
            break
          }

          case 'done': {
            const newConversationId = (data as Record<string, unknown>)
              .conversation_id as string | undefined
            if (newConversationId) {
              setConversationId(newConversationId)
            }
            break
          }
        }
      }
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : 'Something went wrong'
      setMessages((prev) => {
        const updated = [...prev]
        const last = updated[updated.length - 1]
        if (last && last.role === 'assistant') {
          updated[updated.length - 1] = {
            ...last,
            content: last.content || `Sorry, an error occurred: ${errorMessage}`,
          }
        }
        return updated
      })
    } finally {
      setIsStreaming(false)
    }
  }

  // Collapsed state: floating button
  if (!isOpen) {
    return (
      <button
        onClick={onToggle}
        className="fixed bottom-6 right-6 w-14 h-14 rounded-full bg-blue-600 text-white shadow-lg shadow-blue-600/25 hover:bg-blue-500 hover:shadow-blue-500/30 transition-all flex items-center justify-center z-50"
        aria-label="Open chat"
      >
        <svg className="w-6 h-6" viewBox="0 0 20 20" fill="currentColor">
          <path
            fillRule="evenodd"
            d="M18 10c0 3.866-3.582 7-8 7a8.841 8.841 0 01-4.083-.98L2 17l1.338-3.123C2.493 12.767 2 11.434 2 10c0-3.866 3.582-7 8-7s8 3.134 8 7zM7 9H5v2h2V9zm8 0h-2v2h2V9zM9 9h2v2H9V9z"
            clipRule="evenodd"
          />
        </svg>
      </button>
    )
  }

  return (
    <div className="w-[400px] shrink-0 flex flex-col bg-gray-900 border-l border-gray-800 h-full">
      {/* Header */}
      <div className="flex items-center justify-between h-14 px-4 border-b border-gray-800">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-green-400" />
          <h2 className="text-sm font-semibold text-gray-100">Coach</h2>
        </div>
        <button
          onClick={onToggle}
          className="w-8 h-8 flex items-center justify-center rounded-lg text-gray-400 hover:bg-gray-800 hover:text-gray-200 transition-colors"
          aria-label="Minimize chat"
        >
          <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
            <path
              fillRule="evenodd"
              d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
              clipRule="evenodd"
            />
          </svg>
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-12 h-12 rounded-full bg-gray-800 flex items-center justify-center mb-3">
              <svg className="w-6 h-6 text-blue-400" viewBox="0 0 20 20" fill="currentColor">
                <path
                  fillRule="evenodd"
                  d="M18 10c0 3.866-3.582 7-8 7a8.841 8.841 0 01-4.083-.98L2 17l1.338-3.123C2.493 12.767 2 11.434 2 10c0-3.866 3.582-7 8-7s8 3.134 8 7zM7 9H5v2h2V9zm8 0h-2v2h2V9zM9 9h2v2H9V9z"
                  clipRule="evenodd"
                />
              </svg>
            </div>
            <p className="text-sm text-gray-400 mb-1">Your training coach</p>
            <p className="text-xs text-gray-500">
              Ask about your training, readiness, or race prep
            </p>
          </div>
        )}
        {messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <ChatInput onSend={handleSend} disabled={isStreaming} />
    </div>
  )
}
