import { useState, type ReactNode } from 'react'
import Sidebar from './Sidebar'
import BottomNav from './BottomNav'
import ChatPanel from '../chat/ChatPanel'

interface ShellProps {
  children: ReactNode
}

export default function Shell({ children }: ShellProps) {
  const [chatOpen, setChatOpen] = useState(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return true
    }
    return window.matchMedia('(min-width: 768px)').matches
  })

  return (
    <div className="flex h-[100dvh] bg-gray-950 text-gray-100 overflow-hidden">
      {/* Desktop sidebar */}
      <div className="hidden md:flex">
        <Sidebar />
      </div>

      <main className="flex-1 min-w-0 overflow-y-auto pb-16 md:pb-0">{children}</main>

      <ChatPanel isOpen={chatOpen} onToggle={() => setChatOpen((v) => !v)} />

      {/* Mobile bottom nav */}
      <BottomNav onChatToggle={() => setChatOpen((v) => !v)} chatOpen={chatOpen} />
    </div>
  )
}
