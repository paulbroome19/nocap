import { NavLink, Outlet } from 'react-router-dom'

const NAV = [
  { to: '/workflows', label: 'Workflows' },
  { to: '/snapshots', label: 'Snapshots' },
  { to: '/runs', label: 'Runs' },
]

export default function App() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="flex min-h-screen">
        <aside className="flex w-60 flex-col border-r border-slate-200 bg-white">
          <div className="border-b border-slate-200 px-6 py-5">
            <span className="text-lg font-semibold tracking-tight">NoCap</span>
            <p className="mt-0.5 text-xs text-slate-500">
              EBA xBRL-CSV submissions
            </p>
          </div>
          <nav className="flex-1 px-3 py-4">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  [
                    'block rounded-md px-3 py-2 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-slate-900 text-white'
                      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900',
                  ].join(' ')
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </aside>

        <main className="flex-1 px-8 py-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
