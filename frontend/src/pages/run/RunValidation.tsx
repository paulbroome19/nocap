import { useMemo, useState } from 'react'
import { downloadRunFile, type RegisterRow } from '../../api/workflows'
import VerdictBanner from '../../components/VerdictBanner'
import { Card, EmptyState, PageHeader } from '../../components/ui'
import { runCrumbs, useRun } from './context'

type Bucket = 'blocking' | 'failure' | 'warning' | 'passed' | 'other'

function bucketOf(r: RegisterRow): Bucket {
  if (r.result === 'PASSED') return 'passed'
  if (r.result === 'FAILED') return r.blocking ? 'blocking' : 'failure'
  if (r.result === 'WARNING') return 'warning'
  return 'other' // NOTE | DEACTIVATED
}

const BUCKET_META: Record<
  Exclude<Bucket, 'other'>,
  { label: string; edge: string; chip: string }
> = {
  blocking: {
    label: 'Blocking failures',
    edge: 'border-l-red-500',
    chip: 'bg-red-100 text-red-800',
  },
  failure: {
    label: 'Non-blocking rule failures',
    edge: 'border-l-amber-500',
    chip: 'bg-amber-100 text-amber-800',
  },
  warning: {
    label: 'Warnings',
    edge: 'border-l-amber-300',
    chip: 'bg-amber-50 text-amber-700',
  },
  passed: {
    label: 'Passed',
    edge: 'border-l-emerald-400',
    chip: 'bg-emerald-50 text-emerald-700',
  },
}

const RESULT_CHIP: Record<string, string> = {
  FAILED: 'bg-red-50 text-red-700 ring-red-600/20',
  WARNING: 'bg-amber-50 text-amber-700 ring-amber-600/20',
  PASSED: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20',
  NOTE: 'bg-sky-50 text-sky-700 ring-sky-600/20',
  DEACTIVATED: 'bg-slate-100 text-slate-500 ring-slate-500/15',
}

function groupByTemplate(rows: RegisterRow[]): [string, RegisterRow[]][] {
  const m = new Map<string, RegisterRow[]>()
  for (const r of rows) {
    const key = r.template ?? '—'
    const arr = m.get(key)
    if (arr) arr.push(r)
    else m.set(key, [r])
  }
  return [...m.entries()].sort(([a], [b]) => {
    if (a === '—') return 1
    if (b === '—') return -1
    return a.localeCompare(b)
  })
}

function FindingRow({ row }: { row: RegisterRow }) {
  const [open, setOpen] = useState(false)
  const bucket = bucketOf(row)
  const edge =
    bucket === 'blocking'
      ? 'border-l-red-500'
      : bucket === 'failure' || bucket === 'warning'
        ? 'border-l-amber-400'
        : bucket === 'passed'
          ? 'border-l-emerald-300'
          : 'border-l-slate-200'
  const evals = row.evaluations ?? []
  const hasEvalDetail = row.source === 'formula' && evals.length > 0
  const provenance = row.source === 'formula' ? row.rule_text : row.description

  return (
    <div className={`border-l-2 ${edge} bg-white`}>
      <div className="flex items-start gap-3 px-4 py-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs tabular-nums text-slate-500">
              {row.id}
            </span>
            <span className="text-sm font-medium text-slate-800">{row.rule}</span>
            {bucket === 'blocking' && (
              <span className="rounded bg-red-600 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
                Blocking
              </span>
            )}
            {row.source === 'formula' && row.severity == null && (
              <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500">
                severity unknown
              </span>
            )}
          </div>
          {row.detail && (
            <p className="mt-1 text-xs text-slate-600">{row.detail}</p>
          )}
          {provenance && (
            <p className="mt-1 text-[11px] text-slate-400">{provenance}</p>
          )}

          {/* Formula: counts + per-evaluation detail, never a bare number. */}
          {row.source === 'formula' &&
            (row.satisfied != null || row.not_satisfied != null) && (
              <div className="mt-1.5 flex items-center gap-2 text-[11px] text-slate-500">
                <span className="tabular-nums">
                  {row.satisfied ?? 0} satisfied · {row.not_satisfied ?? 0} not
                  satisfied
                </span>
                {hasEvalDetail && (
                  <button
                    type="button"
                    onClick={() => setOpen((o) => !o)}
                    className="font-medium text-slate-600 underline-offset-2 hover:text-slate-900 hover:underline"
                  >
                    {open ? 'Hide evaluations' : `Show ${evals.length} failing`}
                  </button>
                )}
              </div>
            )}
          {open && hasEvalDetail && (
            <div className="mt-2 overflow-hidden rounded-md border border-slate-200">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-slate-50 text-left text-[10px] font-medium uppercase tracking-wide text-slate-400">
                    <th className="px-3 py-1.5 font-medium">Context</th>
                    <th className="px-3 py-1.5 font-medium">Compared</th>
                    <th className="px-3 py-1.5 font-medium">Verdict</th>
                  </tr>
                </thead>
                <tbody>
                  {evals.map((e, i) => (
                    <tr key={i} className="border-t border-slate-100">
                      <td className="px-3 py-1.5 font-mono tabular-nums text-slate-600">
                        {e.template_code
                          ? `${e.template_code} r${e.row_code} c${e.column_code}`
                          : '—'}
                      </td>
                      <td className="px-3 py-1.5 font-mono tabular-nums text-slate-700">
                        {e.values ?? '—'}
                      </td>
                      <td className="px-3 py-1.5 text-red-600">not satisfied</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        <span
          className={`shrink-0 rounded px-1.5 py-0.5 text-[11px] font-semibold ring-1 ring-inset ${
            RESULT_CHIP[row.result] ?? RESULT_CHIP.NOTE
          }`}
        >
          {row.result}
        </span>
      </div>
    </div>
  )
}

function Section({
  bucket,
  rows,
}: {
  bucket: Exclude<Bucket, 'other'>
  rows: RegisterRow[]
}) {
  if (rows.length === 0) return null
  const meta = BUCKET_META[bucket]
  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <h2 className="text-sm font-semibold text-slate-900">{meta.label}</h2>
        <span
          className={`rounded-full px-2 py-0.5 text-[11px] font-semibold tabular-nums ${meta.chip}`}
        >
          {rows.length}
        </span>
      </div>
      <div className="space-y-4">
        {groupByTemplate(rows).map(([template, group]) => (
          <Card key={template} className="overflow-hidden">
            <div className="border-b border-slate-100 bg-slate-50/70 px-4 py-2">
              <span className="font-mono text-xs font-semibold text-slate-600">
                {template === '—' ? 'General' : template}
              </span>
            </div>
            <div className="divide-y divide-slate-100">
              {group.map((r, i) => (
                <FindingRow key={`${r.id}-${i}`} row={r} />
              ))}
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}

export default function RunValidation() {
  const ctx = useRun()
  const { detail } = ctx
  const rows = detail.rule_register
  const report = detail.files.find((f) => f.role === 'validation_report')

  const [filter, setFilter] = useState<'all' | Bucket>('all')
  const [template, setTemplate] = useState<string>('all')
  const [showPassed, setShowPassed] = useState(false)
  const [showOther, setShowOther] = useState(false)

  const byBucket = useMemo(() => {
    const b: Record<Bucket, RegisterRow[]> = {
      blocking: [], failure: [], warning: [], passed: [], other: [],
    }
    const scoped =
      template === 'all' ? rows : rows.filter((r) => r.template === template)
    for (const r of scoped) b[bucketOf(r)].push(r)
    return b
  }, [rows, template])

  const templates = useMemo(
    () => [...new Set(rows.map((r) => r.template).filter(Boolean))].sort(),
    [rows],
  )

  const chip = (key: 'all' | Bucket, label: string, n: number) => (
    <button
      key={key}
      type="button"
      onClick={() => setFilter(key)}
      className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
        filter === key
          ? 'bg-slate-900 text-white'
          : 'bg-white text-slate-600 ring-1 ring-inset ring-slate-200 hover:bg-slate-50'
      }`}
    >
      {label}
      <span className="ml-1.5 tabular-nums opacity-70">{n}</span>
    </button>
  )

  const showBucket = (b: Bucket) => filter === 'all' || filter === b

  return (
    <section className="space-y-5">
      <PageHeader
        crumbs={runCrumbs(ctx, 'Validation')}
        title="Validation"
        actions={
          report && report.available ? (
            <button
              type="button"
              onClick={() => void downloadRunFile(report.id, report.filename)}
              className="text-xs font-medium text-slate-500 underline-offset-2 hover:text-slate-900 hover:underline"
            >
              Download report (HTML)
            </button>
          ) : undefined
        }
      />

      <VerdictBanner verdict={detail.verdict} />

      <div className="flex flex-wrap items-center gap-2">
        {chip('all', 'All', rows.length)}
        {chip('blocking', 'Blocking', byBucket.blocking.length)}
        {chip('failure', 'Non-blocking', byBucket.failure.length)}
        {chip('warning', 'Warnings', byBucket.warning.length)}
        {chip('passed', 'Passed', byBucket.passed.length)}
        {templates.length > 0 && (
          <select
            value={template}
            onChange={(e) => setTemplate(e.target.value)}
            className="ml-auto rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-700 focus:border-slate-400 focus:outline-none"
          >
            <option value="all">All templates</option>
            {templates.map((t) => (
              <option key={t} value={t as string}>
                {t}
              </option>
            ))}
          </select>
        )}
      </div>

      {rows.length === 0 && (
        <EmptyState>No validation results yet for this run.</EmptyState>
      )}

      {/* Lead with what needs attention. */}
      <div className="space-y-6">
        {showBucket('blocking') && (
          <Section bucket="blocking" rows={byBucket.blocking} />
        )}
        {showBucket('failure') && (
          <Section bucket="failure" rows={byBucket.failure} />
        )}
        {showBucket('warning') && (
          <Section bucket="warning" rows={byBucket.warning} />
        )}

        {/* Passed — summarised and collapsed by default. */}
        {(filter === 'all' || filter === 'passed') &&
          byBucket.passed.length > 0 &&
          (filter === 'passed' || showPassed ? (
            <div>
              {filter === 'all' && (
                <button
                  type="button"
                  onClick={() => setShowPassed(false)}
                  className="mb-2 text-xs font-medium text-slate-500 hover:text-slate-900"
                >
                  Hide passed
                </button>
              )}
              <Section bucket="passed" rows={byBucket.passed} />
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setShowPassed(true)}
              className="w-full rounded-lg border border-dashed border-slate-200 bg-white px-4 py-3 text-center text-xs font-medium text-slate-500 hover:border-slate-300 hover:text-slate-700"
            >
              {byBucket.passed.length} checks passed — view
            </button>
          ))}

        {/* Informational: notes + workbook-deactivated rules, collapsed. */}
        {filter === 'all' &&
          byBucket.other.length > 0 &&
          (showOther ? (
            <Card className="overflow-hidden">
              <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50/70 px-4 py-2">
                <span className="text-xs font-semibold text-slate-500">
                  Informational
                </span>
                <button
                  type="button"
                  onClick={() => setShowOther(false)}
                  className="text-xs font-medium text-slate-500 hover:text-slate-900"
                >
                  Hide
                </button>
              </div>
              <div className="divide-y divide-slate-100">
                {byBucket.other.map((r, i) => (
                  <FindingRow key={`${r.id}-${i}`} row={r} />
                ))}
              </div>
            </Card>
          ) : (
            <button
              type="button"
              onClick={() => setShowOther(true)}
              className="w-full rounded-lg border border-dashed border-slate-200 bg-white px-4 py-3 text-center text-xs font-medium text-slate-500 hover:border-slate-300 hover:text-slate-700"
            >
              {byBucket.other.length} informational (notes · deactivated) — view
            </button>
          ))}
      </div>
    </section>
  )
}
