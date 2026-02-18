import { useState, type ReactNode } from 'react'
import Sidebar from './Sidebar'
import ChatPanel from '../chat/ChatPanel'

interface ShellProps {
  children: ReactNode
}

export default function Shell({ children }: ShellProps) {
  const [chatOpen, setChatOpen] = useState(true)

  return (
    <div className="flex h-screen bg-gray-950 text-gray-100 overflow-hidden">
      <Sidebar />

      <main className="flex-1 overflow-y-auto">{children}</main>

      <ChatPanel isOpen={chatOpen} onToggle={() => setChatOpen((v) => !v)} />
    </div>
  )
}
