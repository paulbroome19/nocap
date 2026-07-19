import { NavLink, Outlet } from 'react-router-dom'
import { MarkBadge } from './components/Wheel'

// The primary sections. This list is the single place sections are declared.
const NAV = [
  { to: '/reporting', label: 'Reporting' },
  { to: '/releases', label: 'Taxonomies' },
  { to: '/reference', label: 'Reference Data' },
  { to: '/settings', label: 'Settings' },
]

export default function App() {
  return (
    <div className="min-h-screen bg-canvas text-ink">
      {/* Sidebar — ink panel (§5) */}
      <aside className="fixed inset-y-0 left-0 flex w-[252px] flex-col bg-ink">
        {/* Identity */}
        <div className="px-6 pb-6 pt-7">
          <div className="flex items-center gap-3">
            <MarkBadge size={40} />
            <span className="font-slab text-[26px] font-bold leading-none tracking-[0.01em] text-white">
              Carter
            </span>
          </div>
          <div className="mt-4 text-[9px] font-semibold uppercase leading-[1.5] tracking-[0.2em] text-[#8A8A8A]">
            International Regulatory Reporting
          </div>
          {/* Brand rule — the sidebar's single red signature (§3, §8) */}
          <div className="mt-3.5 h-[2px] w-11 bg-red" />
        </div>

        {/* Nav — text only; gold left-rule + red text when active */}
        <nav className="mt-2 flex flex-col">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                [
                  'block border-l-[3px] py-3 pl-5 pr-[26px] text-[13px] tracking-[0.04em] transition-colors',
                  isActive
                    ? 'border-gold font-bold text-red'
                    : 'border-transparent text-[#CFCFCF] hover:text-white',
                ].join(' ')
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      {/* Content — on canvas grey */}
      <main className="min-h-screen pl-[252px]">
        <div className="mx-auto max-w-5xl px-10 py-9">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
