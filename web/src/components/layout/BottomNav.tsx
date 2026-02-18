import { NavLink } from 'react-router-dom'

const navItems = [
  {
    to: '/',
    label: 'Home',
    icon: (
      <svg className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
        <path d="M10.707 2.293a1 1 0 00-1.414 0l-7 7a1 1 0 001.414 1.414L4 10.414V17a1 1 0 001 1h2a1 1 0 001-1v-2a1 1 0 011-1h2a1 1 0 011 1v2a1 1 0 001 1h2a1 1 0 001-1v-6.586l.293.293a1 1 0 001.414-1.414l-7-7z" />
      </svg>
    ),
  },
  {
    to: '/plan',
    label: 'Plan',
    icon: (
      <svg className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
        <path
          fillRule="evenodd"
          d="M6 2a1 1 0 00-1 1v1H4a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2h-1V3a1 1 0 10-2 0v1H7V3a1 1 0 00-1-1zm0 5a1 1 0 000 2h8a1 1 0 100-2H6z"
          clipRule="evenodd"
        />
      </svg>
    ),
  },
  {
    to: '/races',
    label: 'Races',
    icon: (
      <svg className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
        <path
          fillRule="evenodd"
          d="M3 6a3 3 0 013-3h10a1 1 0 01.8 1.6L14.25 8l2.55 3.4A1 1 0 0116 13H6a1 1 0 00-1 1v3a1 1 0 11-2 0V6z"
          clipRule="evenodd"
        />
      </svg>
    ),
  },
  {
    to: '/profile',
    label: 'Profile',
    icon: (
      <svg className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
        <path
          fillRule="evenodd"
          d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z"
          clipRule="evenodd"
        />
      </svg>
    ),
  },
]

interface BottomNavProps {
  onChatToggle: () => void
  chatOpen: boolean
}

export default function BottomNav({ onChatToggle, chatOpen }: BottomNavProps) {
  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 z-40 bg-gray-900 border-t border-gray-800 flex items-center justify-around px-1 h-16 safe-area-pb">
      {navItems.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === '/'}
          className={({ isActive }) =>
            `flex flex-col items-center gap-0.5 px-3 py-1.5 rounded-lg text-[10px] font-medium transition-colors ${
              isActive
                ? 'text-blue-400'
                : 'text-gray-500 active:text-gray-300'
            }`
          }
        >
          {item.icon}
          <span>{item.label}</span>
        </NavLink>
      ))}
      <button
        onClick={onChatToggle}
        className={`flex flex-col items-center gap-0.5 px-3 py-1.5 rounded-lg text-[10px] font-medium transition-colors ${
          chatOpen ? 'text-blue-400' : 'text-gray-500 active:text-gray-300'
        }`}
      >
        <svg className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
          <path
            fillRule="evenodd"
            d="M18 10c0 3.866-3.582 7-8 7a8.841 8.841 0 01-4.083-.98L2 17l1.338-3.123C2.493 12.767 2 11.434 2 10c0-3.866 3.582-7 8-7s8 3.134 8 7zM7 9H5v2h2V9zm8 0h-2v2h2V9zM9 9h2v2H9V9z"
            clipRule="evenodd"
          />
        </svg>
        <span>Coach</span>
      </button>
    </nav>
  )
}
