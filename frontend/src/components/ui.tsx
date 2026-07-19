// Shared UI primitives — the Carter design system (docs/design-spec.pdf).
// Every screen consumes these; tokens live in index.css (@theme).

import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

export type Crumb = { label: string; to?: string }

/* ── Page title + rule (§6) ─────────────────────────────────────────────── */

/** Breadcrumb trail (13px, muted, links in sub, " / " separator). */
export function Breadcrumb({ items }: { items: Crumb[] }) {
  return (
    <nav className="mb-3.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-muted">
      {items.map((c, i) => {
        const last = i === items.length - 1
        return (
          <span key={i} className="flex items-center gap-2">
            {c.to && !last ? (
              <Link to={c.to} className="text-sub transition-colors hover:text-ink">
                {c.label}
              </Link>
            ) : (
              <span className={last ? 'text-muted' : 'text-sub'}>{c.label}</span>
            )}
            {!last && <span className="text-faint">/</span>}
          </span>
        )
      })}
    </nav>
  )
}

/** The 3px × 48px gold rule that sits under every page title. */
export function TitleRule() {
  return <div className="mt-3 h-[3px] w-12 bg-gold" />
}

/** Page heading: optional breadcrumb, the H1 (HN 700 · 32px · -.02em), the gold
 *  title rule, an optional right-aligned action, and an optional subtitle. */
export function PageHeader({
  title,
  subtitle,
  crumbs,
  actions,
}: {
  title: ReactNode
  subtitle?: ReactNode
  crumbs?: Crumb[]
  actions?: ReactNode
}) {
  return (
    <div className="mb-8">
      {crumbs && <Breadcrumb items={crumbs} />}
      <div className="flex items-start justify-between gap-6">
        <div className="min-w-0">
          <h1 className="text-[32px] font-bold leading-none tracking-[-0.02em] text-ink">
            {title}
          </h1>
          <TitleRule />
          {subtitle && (
            <p className="mt-4 max-w-2xl text-[14px] text-sub">{subtitle}</p>
          )}
        </div>
        {actions && <div className="shrink-0 pt-1">{actions}</div>}
      </div>
    </div>
  )
}

/** Section overline above a block (11px · 700 · .12em caps · muted). */
export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <div className="mb-2.5 text-[11px] font-bold uppercase tracking-[0.14em] text-muted">
      {children}
    </div>
  )
}

/* ── Block (card) anatomy (§4) ──────────────────────────────────────────── */

/** White block: 14px radius, 1px card border, the card shadow, clipped. */
export function Block({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={`overflow-hidden rounded-[14px] border border-card bg-page shadow-card ${className}`}
    >
      {children}
    </div>
  )
}

/** Back-compat alias — existing screens import `Card`. */
export const Card = Block

/** One row inside a block: 22/24 padding, top divider from the 2nd row down. */
export function Row({
  children,
  className = '',
  hover = false,
}: {
  children: ReactNode
  className?: string
  hover?: boolean
}) {
  return (
    <div
      className={`flex items-center justify-between gap-4 border-t border-divider px-6 py-[22px] first:border-t-0 ${
        hover ? 'transition-colors hover:bg-hover' : ''
      } ${className}`}
    >
      {children}
    </div>
  )
}

/** A navigable row: row title (HN 600 · 15px), optional mono sub, → affordance. */
export function RowLink({
  to,
  title,
  subtitle,
  right,
}: {
  to: string
  title: ReactNode
  subtitle?: ReactNode
  right?: ReactNode
}) {
  return (
    <Link
      to={to}
      className="group flex items-center justify-between gap-4 border-t border-divider px-6 py-[22px] transition-colors first:border-t-0 hover:bg-hover"
    >
      <div className="min-w-0">
        <div className="truncate text-[15px] font-semibold text-ink">{title}</div>
        {subtitle && (
          <div className="mt-1 truncate font-mono text-[12px] text-muted">
            {subtitle}
          </div>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-4">
        {right}
        <span className="text-[18px] leading-none text-faint">→</span>
      </div>
    </Link>
  )
}

/** A big mono figure (Plex Mono 500 · ~32px · -.02em). */
export function Figure({
  children,
  className = '',
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <span
      className={`font-mono text-[32px] font-medium leading-none tracking-[-0.02em] text-ink ${className}`}
    >
      {children}
    </span>
  )
}

/* ── States ─────────────────────────────────────────────────────────────── */

/** Dashed empty-state box. */
export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-[14px] border border-dashed border-faint bg-page px-6 py-16 text-center text-[14px] text-muted">
      {children}
    </div>
  )
}

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-divider ${className}`} />
}

export function CardSkeletons({ count = 4 }: { count?: number }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className="h-24" />
      ))}
    </div>
  )
}

export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <Block>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="flex items-center gap-4 border-t border-divider px-6 py-[22px] first:border-t-0"
        >
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="ml-auto h-4 w-16" />
        </div>
      ))}
    </Block>
  )
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return <p className="text-[14px] text-muted">{label}</p>
}

/** Alert/failure text — one of the sanctioned red uses. */
export function ErrorText({ children }: { children: ReactNode }) {
  return children ? <p className="text-[13px] text-red">{children}</p> : null
}

/* ── Inputs, buttons (§7) ───────────────────────────────────────────────── */

export const fieldClass =
  'w-full rounded-[9px] border border-field bg-page px-3 py-2.5 text-[14px] text-ink ' +
  'transition-colors focus:border-muted focus:outline-none ' +
  'disabled:bg-canvas disabled:text-muted'

/** Label sitting above a field (11px muted caps-adjacent). */
export function FieldLabel({ children }: { children: ReactNode }) {
  return (
    <span className="mb-1.5 block text-[11px] font-medium uppercase tracking-[0.08em] text-muted">
      {children}
    </span>
  )
}

/** A styled select with a custom faint caret. */
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
        className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-faint"
      >
        <path d="M6 8l4 4 4-4" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  )
}

/** The ONLY red control on a screen — EXECUTE / CREATE (§7, §8). */
export const primaryBtn =
  'inline-flex items-center justify-center gap-2 rounded-[10px] bg-red px-[30px] py-[13px] ' +
  'text-[13px] font-bold uppercase tracking-[0.12em] text-white transition-colors ' +
  'hover:bg-[#b91a22] disabled:cursor-not-allowed disabled:opacity-40'

/** Neutral secondary action — never red. */
export const secondaryBtn =
  'inline-flex items-center justify-center gap-2 rounded-[10px] border border-field bg-page px-5 py-2.5 ' +
  'text-[13px] font-semibold text-data transition-colors hover:bg-hover ' +
  'disabled:cursor-not-allowed disabled:opacity-40'

/** Restrained destructive text affordance (alert cue only on intent). */
export const dangerText =
  'text-[13px] font-medium text-sub transition-colors hover:text-red disabled:opacity-40'
