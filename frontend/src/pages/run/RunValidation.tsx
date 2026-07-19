import { useMemo, useState } from 'react'
import { downloadRunFile, type RegisterRow } from '../../api/workflows'
import VerdictBanner from '../../components/VerdictBanner'
import { Block, EmptyState, PageHeader, SectionLabel } from '../../components/ui'
import { formatDate } from '../../lib/format'
import { runCrumbs, useRun } from './context'

type Bucket = 'blocking' | 'failure' | 'warning' | 'passed' | 'other'

function bucketOf(r: RegisterRow): Bucket {
  if (r.result === 'PASSED') return 'passed'
  if (r.result === 'FAILED') return r.blocking ? 'blocking' : 'failure'
  if (r.result === 'WARNING') return 'warning'
  return 'other' // NOTE | DEACTIVATED
}

const RESULT_LABEL: Record<RegisterRow['result'], string> = {
  FAILED: 'Failed',
  WARNING: 'Warning',
  PASSED: 'Passed',
  NOTE: 'Note',
  DEACTIVATED: 'Deactivated',
}

/** One rule as a register row, with its per-evaluation detail expandable. */
function RuleRow({ row }: { row: RegisterRow }) {
  const [open, setOpen] = useState(false)
  const bucket = bucketOf(row)
  const failed = row.result === 'FAILED'
  const evals = row.evaluations ?? []
  const hasEvalDetail = row.source === 'formula' && evals.length > 0
  const provenance = row.source === 'formula' ? row.rule_text : row.description
  const counts =
    row.source === 'formula' &&
    (row.satisfied != null || row.not_satisfied != null)
      ? `${row.satisfied ?? 0} satisfied · ${row.not_satisfied ?? 0} not satisfied`
      : null

  return (
    <>
      <tr className="border-t border-divider align-top first:border-t-0">
        <td className="px-6 py-3 font-mono text-[12px] tabular-nums text-muted">
          {row.id}
        </td>
        <td className="px-6 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[13px] font-medium text-data">{row.rule}</span>
            {bucket === 'blocking' && (
              <span className="rounded-[5px] bg-red px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-[0.08em] text-white">
                Blocking
              </span>
            )}
          </div>
          {provenance && (
            <p className="mt-1 text-[12px] leading-snug text-muted">{provenance}</p>
          )}
        </td>
        <td className="px-6 py-3 font-mono text-[12px] tabular-nums text-sub">
          {row.data_evaluated || '—'}
        </td>
        <td className="px-6 py-3">
          <span
            className={`text-[13px] font-medium ${failed ? 'text-red' : 'text-sub'}`}
          >
            {RESULT_LABEL[row.result]}
          </span>
        </td>
        <td className="px-6 py-3 text-[12px] text-sub">
          {row.detail && <p className="leading-snug">{row.detail}</p>}
          {counts && (
            <div className="mt-1 flex flex-wrap items-center gap-2 tabular-nums text-muted">
              <span>{counts}</span>
              {hasEvalDetail && (
                <button
                  type="button"
                  onClick={() => setOpen((o) => !o)}
                  className="font-medium text-data underline-offset-2 hover:underline"
                >
                  {open ? 'Hide detail' : `View ${evals.length} not satisfied`}
                </button>
              )}
            </div>
          )}
        </td>
      </tr>
      {open && hasEvalDetail && (
        <tr className="border-t border-divider bg-canvas">
          <td />
          <td colSpan={4} className="px-6 py-3">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="text-left text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">
                  <th className="py-1 pr-4 font-semibold">Context</th>
                  <th className="py-1 pr-4 font-semibold">Compared</th>
                  <th className="py-1 font-semibold">Result</th>
                </tr>
              </thead>
              <tbody>
                {evals.map((e, i) => (
                  <tr key={i} className="border-t border-divider">
                    <td className="py-1 pr-4 font-mono tabular-nums text-sub">
                      {e.template_code
                        ? `${e.template_code} r${e.row_code} c${e.column_code}`
                        : '—'}
                    </td>
                    <td className="py-1 pr-4 font-mono tabular-nums text-data">
                      {e.values ?? '—'}
                    </td>
                    <td className="py-1 text-red">Not satisfied</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </td>
        </tr>
      )}
    </>
  )
}

function Register({ rows }: { rows: RegisterRow[] }) {
  return (
    <Block className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-b border-divider text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
              <th className="px-6 py-2.5 font-semibold">ID</th>
              <th className="px-6 py-2.5 font-semibold">Rule</th>
              <th className="px-6 py-2.5 font-semibold">Data evaluated</th>
              <th className="px-6 py-2.5 font-semibold">Result</th>
              <th className="px-6 py-2.5 font-semibold">Detail</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <RuleRow key={`${r.id}-${i}`} row={r} />
            ))}
          </tbody>
        </table>
      </div>
    </Block>
  )
}

export default function RunValidation() {
  const ctx = useRun()
  const { detail } = ctx
  const rows = detail.rule_register
  const report = detail.files.find((f) => f.role === 'validation_report')
  const [showPassed, setShowPassed] = useState(false)
  const [showOther, setShowOther] = useState(false)

  const byBucket = useMemo(() => {
    const b: Record<Bucket, RegisterRow[]> = {
      blocking: [], failure: [], warning: [], passed: [], other: [],
    }
    for (const r of rows) b[bucketOf(r)].push(r)
    return b
  }, [rows])

  return (
    <section className="space-y-6">
      <PageHeader
        crumbs={runCrumbs(ctx, 'Validation')}
        title="Validation"
        actions={
          report && report.available ? (
            <button
              type="button"
              onClick={() => void downloadRunFile(report.id, report.filename)}
              className="text-[13px] font-medium text-sub underline-offset-2 hover:text-data hover:underline"
            >
              Download report
            </button>
          ) : undefined
        }
      />

      <VerdictBanner verdict={detail.verdict} />

      {detail.run.rule_scope && (
        <p className="text-[13px] text-sub">
          {detail.run.rule_scope.count.toLocaleString()} rules applicable
          {detail.run.rule_scope.module_code &&
            ` to ${detail.run.rule_scope.module_code} ${detail.run.rule_scope.module_version ?? ''}`.trimEnd()}
          {' at '}
          {formatDate(detail.run.rule_scope.reference_date)}
        </p>
      )}

      {rows.length === 0 ? (
        <EmptyState>No validation results yet for this run.</EmptyState>
      ) : (
        <div className="space-y-8">
          {/* Blocking first — what stops submission. */}
          {byBucket.blocking.length > 0 && (
            <div>
              <SectionLabel>Blocking failures</SectionLabel>
              <div className="mt-2.5">
                <Register rows={byBucket.blocking} />
              </div>
            </div>
          )}

          {/* Then non-blocking rule failures and warnings. */}
          {byBucket.failure.length > 0 && (
            <div>
              <SectionLabel>Non-blocking failures</SectionLabel>
              <div className="mt-2.5">
                <Register rows={byBucket.failure} />
              </div>
            </div>
          )}

          {byBucket.warning.length > 0 && (
            <div>
              <SectionLabel>Warnings</SectionLabel>
              <div className="mt-2.5">
                <Register rows={byBucket.warning} />
              </div>
            </div>
          )}

          {/* Passed — collapsed by default. */}
          {byBucket.passed.length > 0 && (
            <div>
              {showPassed ? (
                <>
                  <div className="mb-2.5 flex items-center justify-between">
                    <SectionLabel>Passed</SectionLabel>
                    <button
                      type="button"
                      onClick={() => setShowPassed(false)}
                      className="text-[13px] font-medium text-sub hover:text-data"
                    >
                      Hide
                    </button>
                  </div>
                  <Register rows={byBucket.passed} />
                </>
              ) : (
                <button
                  type="button"
                  onClick={() => setShowPassed(true)}
                  className="w-full rounded-[10px] border border-dashed border-faint bg-page px-4 py-3 text-center text-[13px] font-medium text-sub hover:border-muted hover:text-data"
                >
                  {byBucket.passed.length} checks passed — view
                </button>
              )}
            </div>
          )}

          {/* Informational: notes and deactivated rules, collapsed. */}
          {byBucket.other.length > 0 && (
            <div>
              {showOther ? (
                <>
                  <div className="mb-2.5 flex items-center justify-between">
                    <SectionLabel>Informational</SectionLabel>
                    <button
                      type="button"
                      onClick={() => setShowOther(false)}
                      className="text-[13px] font-medium text-sub hover:text-data"
                    >
                      Hide
                    </button>
                  </div>
                  <Register rows={byBucket.other} />
                </>
              ) : (
                <button
                  type="button"
                  onClick={() => setShowOther(true)}
                  className="w-full rounded-[10px] border border-dashed border-faint bg-page px-4 py-3 text-center text-[13px] font-medium text-sub hover:border-muted hover:text-data"
                >
                  {byBucket.other.length} informational — view
                </button>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  )
}
