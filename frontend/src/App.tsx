import type { ReactNode } from 'react'
import { NavLink, Outlet } from 'react-router-dom'

type NavItem = { to: string; label: string; icon: ReactNode }

// The primary sections. This list is the single place sections are declared —
// adding a future fifth section is one more entry here, nothing else.
// prettier-ignore
const NAV: NavItem[] = [
  {
    to: '/reporting',
    label: 'Reporting',
    icon: <path d="M4 5h16M4 12h16M4 19h10" strokeWidth="1.75" strokeLinecap="round" />,
  },
  {
    to: '/releases',
    label: 'Taxonomies',
    icon: (
      <path
        d="M4 7l8-4 8 4-8 4-8-4zm0 5l8 4 8-4M4 17l8 4 8-4"
        strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
      />
    ),
  },
  {
    to: '/reference',
    label: 'Reference Data',
    icon: (
      <path
        d="M12 12a3.5 3.5 0 100-7 3.5 3.5 0 000 7zm-7 7a7 7 0 0114 0"
        strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"
      />
    ),
  },
  {
    to: '/settings',
    label: 'Settings',
    icon: (
      <path
        d="M12 15a3 3 0 100-6 3 3 0 000 6zm7.4-3a7.5 7.5 0 00-.1-1.1l2-1.5-2-3.4-2.3.9a7.4 7.4 0 00-1.9-1.1L15.7 2h-3.9l-.4 2.7a7.4 7.4 0 00-1.9 1.1l-2.3-.9-2 3.4 2 1.5a7.6 7.6 0 000 2.2l-2 1.5 2 3.4 2.3-.9c.6.5 1.2.8 1.9 1.1l.4 2.7h3.9l.4-2.7c.7-.3 1.3-.6 1.9-1.1l2.3.9 2-3.4-2-1.5c.1-.4.1-.7.1-1.1z"
        strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"
      />
    ),
  },
]

export default function App() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      {/* App header — dark chrome */}
      <header className="fixed inset-x-0 top-0 z-20 flex h-14 items-center gap-2.5 border-b border-slate-800 bg-slate-950 px-5">
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-white text-sm font-bold text-slate-950">
          N
        </div>
        <span className="text-[15px] font-semibold tracking-tight text-white">
          NoCap
        </span>
        <span className="ml-1 hidden text-[11px] font-medium uppercase tracking-widest text-slate-500 sm:inline">
          Regulatory Reporting
        </span>
      </header>

      <div className="flex pt-14">
        {/* Side nav — dark chrome */}
        <aside className="fixed bottom-0 top-14 w-56 border-r border-slate-800 bg-slate-950">
          <nav className="space-y-0.5 p-3">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  [
                    'group relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-slate-800 text-white'
                      : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200',
                  ].join(' ')
                }
              >
                {({ isActive }) => (
                  <>
                    {isActive && (
                      <span className="absolute inset-y-1.5 left-0 w-0.5 rounded-full bg-white" />
                    )}
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      className="h-[18px] w-[18px] shrink-0"
                    >
                      {item.icon}
                    </svg>
                    {item.label}
                  </>
                )}
              </NavLink>
            ))}
          </nav>
        </aside>

        {/* Content */}
        <main className="ml-56 min-h-[calc(100vh-3.5rem)] min-w-0 flex-1 px-8 py-8">
          <div className="mx-auto max-w-5xl">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
