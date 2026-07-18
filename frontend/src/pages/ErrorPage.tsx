import { isRouteErrorResponse, Link, useRouteError } from 'react-router-dom'
import { primaryBtn } from '../components/ui'

/**
 * Root error boundary — rendered *outside* the app layout when a route throws
 * (loader/render error, or an unmatched route with no catch-all). Carries its
 * own NoCap header so it stays on-brand, and never shows the default developer
 * error page.
 */
export default function ErrorPage() {
  const err = useRouteError()
  const is404 = isRouteErrorResponse(err) && err.status === 404

  const heading = is404 ? 'Page not found' : 'Something went wrong'
  const detail = is404
    ? 'That page doesn’t exist.'
    : err instanceof Error
      ? err.message
      : isRouteErrorResponse(err)
        ? `${err.status} ${err.statusText}`
        : 'An unexpected error occurred.'

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="flex h-14 items-center gap-2.5 border-b border-slate-800 bg-slate-950 px-5">
        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-white text-sm font-bold text-slate-950">
          N
        </div>
        <span className="text-[15px] font-semibold tracking-tight text-white">
          NoCap
        </span>
      </header>

      <div className="flex min-h-[calc(100vh-3.5rem)] items-center justify-center px-6">
        <div className="text-center">
          <div className="font-mono text-6xl font-semibold text-slate-200">
            {is404 ? '404' : 'Error'}
          </div>
          <h1 className="mt-4 text-xl font-semibold tracking-tight text-slate-900">
            {heading}
          </h1>
          <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">{detail}</p>
          <Link to="/reporting" className={`${primaryBtn} mt-6 inline-block`}>
            Back to Reporting
          </Link>
        </div>
      </div>
    </div>
  )
}
