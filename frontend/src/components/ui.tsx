// Shared UI primitives — keeps page layout, spacing, and states consistent.

import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

/** Page heading with an optional back link, subtitle, and right-aligned actions. */
export function PageHeader({
  title,
  subtitle,
  back,
  actions,
}: {
  title: ReactNode
  subtitle?: ReactNode
  back?: { to: string; label: string }
  actions?: ReactNode
}) {
  return (
    <div className="mb-6">
      {back && (
        <Link
          to={back.to}
          className="text-xs text-slate-500 transition-colors hover:text-slate-800"
        >
          ← {back.label}
        </Link>
      )}
      <div className="mt-1 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
            {title}
          </h1>
          {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
        </div>
        {actions && <div className="shrink-0">{actions}</div>}
      </div>
    </div>
  )
}

/** White surface card. */
export function Card({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={`rounded-lg border border-slate-200 bg-white ${className}`}
    >
      {children}
    </div>
  )
}

/** Dashed empty-state box. */
export function EmptyState({
  children,
}: {
  children: ReactNode
}) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white px-6 py-14 text-center text-sm text-slate-400">
      {children}
    </div>
  )
}

/** Centered loading line. */
export function Loading({ label = 'Loading…' }: { label?: string }) {
  return <p className="text-sm text-slate-400">{label}</p>
}

/** Inline error line. */
export function ErrorText({ children }: { children: ReactNode }) {
  return children ? <p className="text-sm text-red-600">{children}</p> : null
}

export const fieldClass =
  'w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-900 ' +
  'focus:border-slate-500 focus:outline-none disabled:bg-slate-50 disabled:text-slate-400'

export const primaryBtn =
  'rounded-md bg-slate-900 px-4 py-1.5 text-sm font-medium text-white ' +
  'transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40'

export const secondaryBtn =
  'rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 ' +
  'transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40'

export const fileInputClass =
  'text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 ' +
  'file:px-3 file:py-1.5 file:text-sm file:font-medium hover:file:bg-slate-200'
