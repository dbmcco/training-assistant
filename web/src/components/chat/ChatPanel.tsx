import { useState, useRef, useEffect, useCallback } from 'react'
import { useLocation } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  fetchConversation,
  fetchConversations,
  fetchDashboardToday,
  fetchRecommendations,
  generateBriefing,
  streamChat,
  submitRecommendationDecision,
} from '../../api/client'
import ChatMessage from './ChatMessage'
import ChatInput from './ChatInput'
import type { Message } from './ChatMessage'
import type {
  Briefing,
  ChatMessage as ApiChatMessage,
  ConversationDetail,
  RecommendationDecision,
} from '../../api/types'

interface ChatPanelProps {
  isOpen: boolean
  onToggle: () => void
}

const CONVERSATION_STORAGE_KEY = 'training-assistant-conversation-id'
const DEFAULT_VISIBLE_MESSAGES = 12
const CONVERSATION_FETCH_LIMIT = 120

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

function routeLabel(pathname: string): string {
  switch (pathname) {
    case '/':
      return 'dashboard'
    case '/plan':
      return 'plan'
    case '/analysis':
      return 'analysis'
    case '/races':
      return 'plan'
    case '/profile':
      return 'profile'
    default:
      return 'unknown'
  }
}

function briefingToMessage(briefing: Briefing): Message {
  const lines: string[] = ['## Daily Briefing']
  if (briefing.content) {
    lines.push(briefing.content)
  }
  if (briefing.readiness_summary) {
    lines.push(`### Readiness\n${briefing.readiness_summary}`)
  }
  if (briefing.workout_recommendation) {
    lines.push(`### Workout Recommendation\n${briefing.workout_recommendation}`)
  }
  if (briefing.alerts && briefing.alerts.length > 0) {
    lines.push('### Alerts')
    for (const alert of briefing.alerts) {
      lines.push(`- ${alert}`)
    }
  }

  const recommendationText = briefing.recommendation_change?.recommendation_text
  if (briefing.recommendation_change && recommendationText) {
    lines.push(`### Proposed Plan Change\n${recommendationText}`)
  }

  return {
    id: `briefing-${Date.now()}`,
    role: 'assistant',
    content: lines.join('\n\n').trim(),
    toolCalls: [],
    recommendationChange: briefing.recommendation_change ?? null,
  }
}

function apiMessageToUi(message: ApiChatMessage): Message {
  const parsedToolCalls = Array.isArray(message.tool_calls)
    ? message.tool_calls
        .map((call) => {
          const nameValue = call['name']
          const statusValue = call['status']
          if (
            typeof nameValue === 'string' &&
            (statusValue === 'calling' || statusValue === 'done')
          ) {
            return { name: nameValue, status: statusValue }
          }
          return null
        })
        .filter((entry): entry is { name: string; status: 'calling' | 'done' } => entry !== null)
    : []

  return {
    id: message.id,
    role: message.role,
    content: message.content,
    toolCalls: parsedToolCalls,
    recommendationChange: null,
  }
}

export default function ChatPanel({ isOpen, onToggle }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [conversationId, setConversationId] = useState<string | undefined>()
  const [decisionBusyId, setDecisionBusyId] = useState<string | null>(null)
  const [showFullHistory, setShowFullHistory] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const hasSeededBriefingRef = useRef(false)
  const hasHydratedConversationRef = useRef(false)
  const location = useLocation()
  const queryClient = useQueryClient()

  const todayQuery = useQuery({
    queryKey: ['dashboard', 'today'],
    queryFn: fetchDashboardToday,
    staleTime: 60_000,
  })

  const conversationSeedQuery = useQuery({
    queryKey: ['chat', 'latestConversation'],
    queryFn: async (): Promise<ConversationDetail | null> => {
      const persistedId =
        typeof window !== 'undefined'
          ? window.localStorage.getItem(CONVERSATION_STORAGE_KEY)
          : null

      if (persistedId) {
        try {
          return await fetchConversation(persistedId, {
            limit: CONVERSATION_FETCH_LIMIT,
          })
        } catch {
          // Continue to latest conversation fallback.
        }
      }

      const conversations = await fetchConversations()
      const latest = conversations[0]
      if (!latest) {
        return null
      }
      return fetchConversation(latest.id, {
        limit: CONVERSATION_FETCH_LIMIT,
      })
    },
    staleTime: 60_000,
  })

  const pendingRecommendationsQuery = useQuery({
    queryKey: ['recommendations', 'pending'],
    queryFn: () => fetchRecommendations({ status: 'pending', limit: 5 }),
    staleTime: 30_000,
    refetchInterval: 60_000,
  })

  useEffect(() => {
    if (hasHydratedConversationRef.current) {
      return
    }

    if (conversationSeedQuery.isSuccess) {
      const conversation = conversationSeedQuery.data
      if (conversation?.id) {
        const hydrated = (conversation.messages ?? []).map(apiMessageToUi)
        setMessages(hydrated)
        setConversationId(conversation.id)
        hasSeededBriefingRef.current = hydrated.some((m) => m.id.startsWith('briefing-'))
      }
      hasHydratedConversationRef.current = true
    }
  }, [conversationSeedQuery.data, conversationSeedQuery.isSuccess])

  useEffect(() => {
    if (!conversationId || typeof window === 'undefined') {
      return
    }
    window.localStorage.setItem(CONVERSATION_STORAGE_KEY, conversationId)
  }, [conversationId])

  useEffect(() => {
    if (conversationSeedQuery.isPending) {
      return
    }
    const briefing = todayQuery.data?.briefing
    if (!briefing || hasSeededBriefingRef.current) {
      return
    }
    setMessages((prev) => [briefingToMessage(briefing), ...prev])
    hasSeededBriefingRef.current = true
  }, [todayQuery.data?.briefing, conversationSeedQuery.isPending])

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  const visibleMessages = showFullHistory
    ? messages
    : messages.slice(-DEFAULT_VISIBLE_MESSAGES)
  const hiddenCount = Math.max(0, messages.length - DEFAULT_VISIBLE_MESSAGES)

  useEffect(() => {
    const pending = pendingRecommendationsQuery.data
    if (!pending || pending.length === 0) {
      return
    }

    setMessages((prev) => {
      const existingRecommendationIds = new Set(
        prev.map((msg) => msg.recommendationChange?.id).filter((id): id is string => Boolean(id)),
      )
      const additions = pending
        .filter((rec) => !existingRecommendationIds.has(rec.id))
        .reverse()
        .map((rec) => ({
          id: `recommendation-${rec.id}`,
          role: 'assistant' as const,
          content:
            rec.recommendation_text ||
            'Proposed plan change is ready for review. Approve to apply and sync.',
          toolCalls: [],
          recommendationChange: rec,
        }))

      if (additions.length === 0) {
        return prev
      }
      return [...prev, ...additions]
    })
  }, [pendingRecommendationsQuery.data])

  const briefingMutation = useMutation({
    mutationFn: generateBriefing,
    onSuccess: (briefing) => {
      const message = briefingToMessage(briefing)
      setMessages((prev) => {
        const withoutOldBriefing = prev.filter((m) => !m.id.startsWith('briefing-'))
        return [message, ...withoutOldBriefing]
      })
      hasSeededBriefingRef.current = true
      queryClient.invalidateQueries({ queryKey: ['dashboard', 'today'] })
    },
  })

  const recommendationDecisionMutation = useMutation({
    mutationFn: ({
      recommendationId,
      decision,
      note,
      requestedChanges,
    }: {
      recommendationId: string
      decision: RecommendationDecision
      note?: string
      requestedChanges?: string
    }) =>
      submitRecommendationDecision(recommendationId, {
        decision,
        note,
        requested_changes: requestedChanges,
      }),
    onSuccess: (updated) => {
      setMessages((prev) =>
        prev.map((msg) =>
          msg.recommendationChange?.id === updated.id
            ? { ...msg, recommendationChange: updated }
            : msg,
        ),
      )
      queryClient.invalidateQueries({ queryKey: ['dashboard', 'today'] })
      queryClient.invalidateQueries({ queryKey: ['planWorkouts'] })
      queryClient.invalidateQueries({ queryKey: ['planAdherence'] })
      queryClient.invalidateQueries({ queryKey: ['recommendations', 'pending'] })
    },
    onSettled: () => setDecisionBusyId(null),
  })

  async function handleRecommendationDecision(
    recommendationId: string,
    decision: RecommendationDecision,
    note?: string,
    requestedChanges?: string,
  ) {
    setDecisionBusyId(recommendationId)
    recommendationDecisionMutation.mutate({
      recommendationId,
      decision,
      note,
      requestedChanges,
    })
  }

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
        const eventType = event.event
        const data = event.data ?? {}

        switch (eventType) {
          case 'token': {
            const token = String(data.content ?? data.token ?? '')
            if (!token) break
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
            const toolName = String(data.tool ?? data.name ?? 'tool')
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
            const toolName = String(data.tool ?? data.name ?? 'tool')
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
            const newConversationId = data.conversation_id as string | undefined
            if (newConversationId) {
              setConversationId(newConversationId)
            }
            const finalContent = typeof data.content === 'string' ? data.content : null
            if (finalContent !== null) {
              setMessages((prev) => {
                const updated = [...prev]
                const last = updated[updated.length - 1]
                if (last && last.role === 'assistant') {
                  updated[updated.length - 1] = { ...last, content: finalContent }
                }
                return updated
              })
            }
            // Do not wait for socket close; once done is received, unlock input.
            return
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

  function handleStartFreshChat() {
    const latestBriefing = todayQuery.data?.briefing
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem(CONVERSATION_STORAGE_KEY)
    }
    setConversationId(undefined)
    setShowFullHistory(false)
    if (latestBriefing) {
      setMessages([briefingToMessage(latestBriefing)])
      hasSeededBriefingRef.current = true
      return
    }
    setMessages([])
    hasSeededBriefingRef.current = false
  }

  // Collapsed state: floating button (desktop only; mobile uses BottomNav)
  if (!isOpen) {
    return (
      <button
        onClick={onToggle}
        className="hidden md:flex fixed bottom-6 right-6 w-14 h-14 rounded-full bg-blue-600 text-white shadow-lg shadow-blue-600/25 hover:bg-blue-500 hover:shadow-blue-500/30 transition-all items-center justify-center z-50"
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
    <div className="fixed inset-0 z-50 md:static md:z-auto md:w-[460px] shrink-0 flex flex-col bg-gray-900 border-l border-gray-800 h-full">
      {/* Header */}
      <div className="flex items-center justify-between h-14 px-4 border-b border-gray-800">
        <div className="flex items-center gap-2">
          <img
            src="/icon-192.png"
            alt="Training Assistant"
            className="w-5 h-5 rounded object-cover"
          />
          <div className="w-2 h-2 rounded-full bg-green-400" />
          <h2 className="text-sm font-semibold text-gray-100">Coach</h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleStartFreshChat}
            className="rounded-lg border border-gray-700 px-2 py-1 text-[11px] text-gray-300 hover:bg-gray-800"
            aria-label="Start a new chat"
          >
            New chat
          </button>
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
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4">
        {messages.length > DEFAULT_VISIBLE_MESSAGES && (
          <div className="mb-3 rounded-lg border border-gray-700/80 bg-gray-900/70 px-3 py-2 text-xs text-gray-300">
            <span className="text-gray-400">
              {showFullHistory
                ? `Showing full history (${messages.length} messages).`
                : `Showing latest ${visibleMessages.length} messages.`}
            </span>{' '}
            <button
              type="button"
              onClick={() => setShowFullHistory((v) => !v)}
              className="text-blue-300 hover:text-blue-200"
            >
              {showFullHistory
                ? `Hide older ${hiddenCount} messages`
                : `Show full history (${messages.length})`}
            </button>
          </div>
        )}
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
            <p className="text-xs text-gray-500 mb-4">
              Daily briefing now lives here in chat
            </p>
            {!todayQuery.data?.briefing && (
              <button
                type="button"
                onClick={() => briefingMutation.mutate()}
                disabled={briefingMutation.isPending}
                className="px-3 py-1.5 rounded-md text-xs font-medium bg-blue-500/15 text-blue-300 border border-blue-500/30 hover:bg-blue-500/25 disabled:opacity-60"
              >
                {briefingMutation.isPending ? 'Generating briefing...' : "Generate today's briefing"}
              </button>
            )}
          </div>
        )}
        {visibleMessages.map((msg) => (
          <ChatMessage
            key={msg.id}
            message={msg}
            decisionBusyId={decisionBusyId}
            onRecommendationDecision={handleRecommendationDecision}
          />
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <ChatInput onSend={handleSend} disabled={isStreaming} />
    </div>
  )
}
