import { Link, useLocation } from 'react-router-dom'
import { secondaryBtn } from '../components/ui'

/** In-shell 404 — rendered inside the app layout (header + sidebar intact). */
export default function NotFound() {
  const { pathname } = useLocation()
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
      <div className="font-mono text-6xl font-medium text-faint">404</div>
      <h1 className="mt-4 font-slab text-[22px] text-ink">Page not found</h1>
      <p className="mt-2 text-[14px] text-sub">
        We couldn&rsquo;t find{' '}
        <span className="font-mono text-data">{pathname}</span>.
      </p>
      <Link to="/reporting" className={`${secondaryBtn} mt-6`}>
        Back to Reporting
      </Link>
    </div>
  )
}
