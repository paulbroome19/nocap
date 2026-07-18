import { Link, useLocation } from 'react-router-dom'
import { primaryBtn } from '../components/ui'

/** In-shell 404 — rendered inside the app layout (header + sidebar intact). */
export default function NotFound() {
  const { pathname } = useLocation()
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
      <div className="font-mono text-6xl font-semibold text-slate-200">404</div>
      <h1 className="mt-4 text-xl font-semibold tracking-tight text-slate-900">
        Page not found
      </h1>
      <p className="mt-1 text-sm text-slate-500">
        We couldn&rsquo;t find{' '}
        <span className="font-mono text-slate-600">{pathname}</span>.
      </p>
      <Link to="/reporting" className={`${primaryBtn} mt-6`}>
        Back to Reporting
      </Link>
    </div>
  )
}
