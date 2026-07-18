// Shared UI primitives — consistent layout, spacing, and states.

import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

export type Crumb = { label: string; to?: string }

/** Breadcrumb trail, e.g. Reporting → Liquidity → LCR. */
export function Breadcrumb({ items }: { items: Crumb[] }) {
  return (
    <nav className="flex items-center gap-1.5 text-xs text-slate-400">
      {items.map((c, i) => {
        const last = i === items.length - 1
        return (
          <span key={i} className="flex items-center gap-1.5">
            {c.to && !last ? (
              <Link to={c.to} className="transition-colors hover:text-slate-700">
                {c.label}
              </Link>
            ) : (
              <span className={last ? 'font-medium text-slate-600' : ''}>
                {c.label}
              </span>
            )}
            {!last && <span className="text-slate-300">/</span>}
          </span>
        )
      })}
    </nav>
  )
}

/** Page heading with optional breadcrumb, subtitle, and right-aligned actions. */
export function PageHeader({
  title,
  subtitle,
  crumbs,
  back,
  actions,
}: {
  title: ReactNode
  subtitle?: ReactNode
  crumbs?: Crumb[]
  back?: { to: string; label: string }
  actions?: ReactNode
}) {
  return (
    <div className="mb-6">
      {crumbs && <Breadcrumb items={crumbs} />}
      {back && !crumbs && (
        <Link
          to={back.to}
          className="text-xs text-slate-500 transition-colors hover:text-slate-800"
        >
          ← {back.label}
        </Link>
      )}
      <div className="mt-2 flex items-start justify-between gap-4">
        <div className="min-w-0">
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

/** A single row in a minimal vertical list (name + chevron). */
export function RowLink({
  to,
  title,
  subtitle,
}: {
  to: string
  title: string
  subtitle?: string
}) {
  return (
    <Link
      to={to}
      className="flex items-center justify-between gap-4 px-4 py-3.5 transition-colors hover:bg-slate-50"
    >
      <div className="min-w-0">
        <div className="truncate text-sm font-medium text-slate-900">
          {title}
        </div>
        {subtitle && (
          <div className="mt-0.5 truncate font-mono text-xs text-slate-400">
            {subtitle}
          </div>
        )}
      </div>
      <span className="shrink-0 text-slate-300">→</span>
    </Link>
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
    <div className={`rounded-lg border border-slate-200 bg-white ${className}`}>
      {children}
    </div>
  )
}

/** Dashed empty-state box. */
export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white px-6 py-14 text-center text-sm text-slate-400">
      {children}
    </div>
  )
}

/** Animated loading placeholder block. */
export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-slate-100 ${className}`} />
}

/** A grid of card skeletons for loading states. */
export function CardSkeletons({ count = 4 }: { count?: number }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className="h-28" />
      ))}
    </div>
  )
}

/** A card-framed table skeleton for list loading states. */
export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <Card className="divide-y divide-slate-100 p-0">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 px-4 py-3.5">
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-4 w-1/4" />
          <Skeleton className="ml-auto h-4 w-16" />
        </div>
      ))}
    </Card>
  )
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return <p className="text-sm text-slate-400">{label}</p>
}

export function ErrorText({ children }: { children: ReactNode }) {
  return children ? <p className="text-sm text-red-600">{children}</p> : null
}

export const fieldClass =
  'w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 ' +
  'transition-colors focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-900/5 ' +
  'disabled:bg-slate-50 disabled:text-slate-400'

/**
 * A styled select with a custom chevron — no browser-default dropdown chrome.
 * Same field language as inputs; children are the `<option>`s.
 */
export function Select({
  value,
  onChange,
  disabled,
  children,
  className = '',
}: {
  value: string | number
  onChange: (v: string) => void
  disabled?: boolean
  children: ReactNode
  className?: string
}) {
  return (
    <div className={`relative ${className}`}>
      <select
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className={`${fieldClass} cursor-pointer appearance-none pr-9`}
      >
        {children}
      </select>
      <svg
        viewBox="0 0 20 20"
        fill="none"
        stroke="currentColor"
        aria-hidden
        className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
      >
        <path d="M6 8l4 4 4-4" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  )
}

export const primaryBtn =
  'rounded-md bg-slate-900 px-4 py-1.5 text-sm font-medium text-white ' +
  'transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40'

export const secondaryBtn =
  'rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 ' +
  'transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40'
