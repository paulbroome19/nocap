import type { ReactNode } from 'react'
import { NavLink, Outlet } from 'react-router-dom'

type NavItem = {
  to: string
  label: string
  hint: string
  icon: ReactNode
}

// prettier-ignore
const NAV: NavItem[] = [
  {
    to: '/reporting',
    label: 'Reporting',
    hint: 'Workflows & runs',
    icon: (
      <path d="M4 5h16M4 12h16M4 19h10" strokeWidth="1.75" strokeLinecap="round" />
    ),
  },
  {
    to: '/releases',
    label: 'Releases',
    hint: 'DPM & taxonomy',
    icon: (
      <path
        d="M4 7l8-4 8 4-8 4-8-4zm0 5l8 4 8-4M4 17l8 4 8-4"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    ),
  },
  {
    to: '/reference',
    label: 'Reference Data',
    hint: 'Entities & config',
    icon: (
      <path
        d="M12 12a3.5 3.5 0 100-7 3.5 3.5 0 000 7zm-7 7a7 7 0 0114 0"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    ),
  },
]

export default function App() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      {/* App header */}
      <header className="sticky top-0 z-10 flex h-14 items-center gap-3 border-b border-slate-200 bg-white px-6">
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-slate-900 text-sm font-bold text-white">
          N
        </div>
        <div className="leading-none">
          <span className="text-base font-semibold tracking-tight">NoCap</span>
        </div>
        <span className="ml-2 hidden text-xs text-slate-400 sm:inline">
          EBA xBRL-CSV regulatory submissions
        </span>
      </header>

      <div className="flex min-h-[calc(100vh-3.5rem)]">
        {/* Side nav */}
        <aside className="w-60 shrink-0 border-r border-slate-200 bg-white">
          <nav className="sticky top-14 space-y-1 px-3 py-5">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  [
                    'flex items-center gap-3 rounded-md px-3 py-2 transition-colors',
                    isActive
                      ? 'bg-slate-900 text-white'
                      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900',
                  ].join(' ')
                }
              >
                {({ isActive }) => (
                  <>
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      className="h-5 w-5 shrink-0"
                    >
                      {item.icon}
                    </svg>
                    <span className="min-w-0">
                      <span className="block text-sm font-medium">
                        {item.label}
                      </span>
                      <span
                        className={[
                          'block text-xs',
                          isActive ? 'text-slate-300' : 'text-slate-400',
                        ].join(' ')}
                      >
                        {item.hint}
                      </span>
                    </span>
                  </>
                )}
              </NavLink>
            ))}
          </nav>
        </aside>

        {/* Content */}
        <main className="min-w-0 flex-1 px-8 py-8">
          <div className="mx-auto max-w-5xl">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
