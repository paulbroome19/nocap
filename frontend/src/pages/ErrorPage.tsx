import { isRouteErrorResponse, Link, useRouteError } from 'react-router-dom'
import { MarkBadge } from '../components/Wheel'
import { secondaryBtn } from '../components/ui'

/**
 * Root error boundary — rendered *outside* the app layout when a route throws
 * (loader/render error, or an unmatched route with no catch-all). Carries its
 * own Carter header so it stays on-brand, and never shows the default developer
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
    <div className="min-h-screen bg-canvas text-ink">
      <header className="flex h-16 items-center gap-3 border-b border-divider bg-page px-6">
        <MarkBadge size={30} />
        <span className="font-slab text-[22px] text-ink">Carter</span>
      </header>

      <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center px-6">
        <div className="text-center">
          <div className="font-mono text-6xl font-medium text-faint">
            {is404 ? '404' : 'Error'}
          </div>
          <h1 className="mt-4 font-slab text-[22px] text-ink">{heading}</h1>
          <p className="mx-auto mt-2 max-w-md text-[14px] text-sub">{detail}</p>
          <Link to="/reporting" className={`${secondaryBtn} mt-6 inline-block`}>
            Back to Reporting
          </Link>
        </div>
      </div>
    </div>
  )
}
