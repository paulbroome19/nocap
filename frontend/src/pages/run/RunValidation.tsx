import { type ReactNode, useMemo, useState } from 'react'
import {
  downloadRunFile,
  type FormulaSummary,
  type RegisterRow,
} from '../../api/workflows'
import VerdictBanner from '../../components/VerdictBanner'
import { Block, EmptyState, PageHeader, SectionLabel } from '../../components/ui'
import { formatDate } from '../../lib/format'
import { runCrumbs, useRun } from './context'

// The page is organised by rule *family*, never by severity — severity shows as
// a per-row badge instead. Informational = notes / deactivated rules (either
// source); the rest split on source.
type Family = 'formula' | 'structural' | 'informational'

function familyOf(r: RegisterRow): Family {
  if (r.result === 'NOTE' || r.result === 'DEACTIVATED') return 'informational'
  return r.source === 'formula' ? 'formula' : 'structural'
}

const RESULT_LABEL: Record<RegisterRow['result'], string> = {
  FAILED: 'Failed',
  WARNING: 'Warning',
  PASSED: 'Passed',
  NOTE: 'Note',
  DEACTIVATED: 'Deactivated',
}
const RESULT_ORDER: Record<RegisterRow['result'], number> = {
  FAILED: 0,
  WARNING: 1,
  PASSED: 2,
  NOTE: 3,
  DEACTIVATED: 4,
}

/** Severity badge: workbook severity for formula rules, blocking/non-blocking
 *  for structural. Red is reserved for the blocking (error) severity. */
function severityBadge(r: RegisterRow): { label: string; cls: string } {
  switch (r.severity) {
    case 'error':
      return { label: 'Blocking', cls: 'text-red' }
    case 'warning':
      return { label: 'Non-blocking', cls: 'text-data' }
    case 'info':
      return { label: 'Info', cls: 'text-muted' }
    default:
      return r.source === 'formula'
        ? { label: 'Unknown', cls: 'text-muted' }
        : { label: '—', cls: 'text-faint' }
  }
}

function counts(rows: RegisterRow[]) {
  const passed = rows.filter((r) => r.result === 'PASSED').length
  const failed = rows.filter((r) => r.result === 'FAILED').length
  const warned = rows.filter((r) => r.result === 'WARNING').length
  return { passed, failed, warned, total: rows.length }
}

function countsLine(label: string, rows: RegisterRow[]): string {
  const c = counts(rows)
  const parts = [`${c.passed}/${c.total} passed`]
  if (c.failed) parts.push(`${c.failed} failed`)
  if (c.warned) parts.push(`${c.warned} warning${c.warned === 1 ? '' : 's'}`)
  return `${label}: ${parts.join(' · ')}`
}

/** One rule, expandable to its code, description, detail, and — for formula
 *  rules — the evaluated comparison from Arelle's output. */
function RuleRow({ row }: { row: RegisterRow }) {
  const [open, setOpen] = useState(false)
  const failed = row.result === 'FAILED'
  const badge = severityBadge(row)
  const isFormula = row.source === 'formula'
  const evals = row.evaluations ?? []
  const expression = isFormula ? row.rule_text : row.description

  return (
    <>
      <tr
        className="cursor-pointer border-t border-divider align-top first:border-t-0 hover:bg-hover"
        onClick={() => setOpen((o) => !o)}
      >
        <td className="px-6 py-3 font-mono text-[12px] tabular-nums text-muted">
          {row.id}
        </td>
        <td className="px-6 py-3">
          <span className="text-[13px] font-medium text-data">{row.rule}</span>
        </td>
        <td className="px-6 py-3">
          <span className={`text-[12px] font-medium ${badge.cls}`}>
            {badge.label}
          </span>
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
        <td className="px-6 py-3 text-right">
          <span className="text-[11px] text-faint">{open ? '▲' : '▼'}</span>
        </td>
      </tr>
      {open && (
        <tr className="border-t border-divider bg-canvas">
          <td />
          <td colSpan={5} className="px-6 py-4">
            <dl className="space-y-3 text-[12px]">
              <div>
                <dt className="font-semibold uppercase tracking-[0.08em] text-[10px] text-muted">
                  Rule
                </dt>
                <dd className="mt-1 font-mono text-data">{row.id}</dd>
              </div>
              {expression && (
                <div>
                  <dt className="font-semibold uppercase tracking-[0.08em] text-[10px] text-muted">
                    {isFormula ? 'Expression' : 'What this checks'}
                  </dt>
                  <dd
                    className={`mt-1 ${isFormula ? 'font-mono' : ''} text-data`}
                  >
                    {expression}
                  </dd>
                </div>
              )}
              {row.detail && (
                <div>
                  <dt className="font-semibold uppercase tracking-[0.08em] text-[10px] text-muted">
                    Detail
                  </dt>
                  <dd className={`mt-1 ${failed ? 'text-red' : 'text-sub'}`}>
                    {row.detail}
                  </dd>
                </div>
              )}
              {isFormula &&
                (row.satisfied != null || row.not_satisfied != null) && (
                  <div>
                    <dt className="font-semibold uppercase tracking-[0.08em] text-[10px] text-muted">
                      Evaluations
                    </dt>
                    <dd className="mt-1 tabular-nums text-sub">
                      {row.satisfied ?? 0} satisfied · {row.not_satisfied ?? 0}{' '}
                      not satisfied
                    </dd>
                  </div>
                )}
              {isFormula && evals.length > 0 && (
                <div>
                  <dt className="font-semibold uppercase tracking-[0.08em] text-[10px] text-muted">
                    Evaluated comparison
                  </dt>
                  <dd className="mt-1.5 overflow-x-auto">
                    <table className="w-full text-[12px]">
                      <thead>
                        <tr className="text-left text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">
                          <th className="py-1 pr-4 font-semibold">Cell</th>
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
                              {e.values ?? e.message ?? '—'}
                            </td>
                            <td className="py-1 text-red">Not satisfied</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </dd>
                </div>
              )}
            </dl>
          </td>
        </tr>
      )}
    </>
  )
}

type ResultFilter = 'failed' | 'passed' | 'all'

function Segmented({
  value,
  onChange,
  options,
}: {
  value: ResultFilter
  onChange: (v: ResultFilter) => void
  options: { value: ResultFilter; label: string }[]
}) {
  return (
    <div className="inline-flex rounded-[8px] border border-field p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          className={`rounded-[6px] px-2.5 py-1 text-[12px] font-medium ${
            value === o.value
              ? 'bg-canvas text-ink'
              : 'text-muted hover:text-data'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

function RuleTable({ rows }: { rows: RegisterRow[] }) {
  return (
    <Block className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-b border-divider text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
              <th className="px-6 py-2.5 font-semibold">ID</th>
              <th className="px-6 py-2.5 font-semibold">Rule</th>
              <th className="px-6 py-2.5 font-semibold">Severity</th>
              <th className="px-6 py-2.5 font-semibold">Data evaluated</th>
              <th className="px-6 py-2.5 font-semibold">Result</th>
              <th className="px-6 py-2.5" />
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

/** A rule-family section: a headline with per-section counts, a Failed/Passed/
 *  All filter, a template filter, and failed-first-sorted rows. */
function Section({
  label,
  title,
  rows,
  defaultOpen,
  showResultFilter = true,
  emptyContent,
}: {
  label: string
  title: string
  rows: RegisterRow[]
  defaultOpen: boolean
  showResultFilter?: boolean
  emptyContent?: ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  const [filter, setFilter] = useState<ResultFilter>('all')
  const [template, setTemplate] = useState<string>('')

  const templates = useMemo(
    () =>
      Array.from(
        new Set(rows.map((r) => r.template).filter((t): t is string => !!t)),
      ).sort(),
    [rows],
  )

  const visible = useMemo(() => {
    const f = rows.filter((r) => {
      if (template && r.template !== template) return false
      if (filter === 'failed')
        return r.result === 'FAILED' || r.result === 'WARNING'
      if (filter === 'passed') return r.result === 'PASSED'
      return true
    })
    return [...f].sort((a, b) => RESULT_ORDER[a.result] - RESULT_ORDER[b.result])
  }, [rows, filter, template])

  const isEmpty = rows.length === 0

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-3 text-left"
      >
        <span className="flex items-baseline gap-3">
          <SectionLabel>{title}</SectionLabel>
          <span className="text-[12px] tabular-nums text-sub">
            {isEmpty ? '—' : countsLine(label, rows).split(': ')[1]}
          </span>
        </span>
        <span className="text-[11px] text-faint">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="mt-3 space-y-3">
          {isEmpty ? (
            emptyContent ?? (
              <EmptyState>No {label.toLowerCase()} rules for this run.</EmptyState>
            )
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-3">
                {showResultFilter && (
                  <Segmented
                    value={filter}
                    onChange={setFilter}
                    options={[
                      { value: 'failed', label: 'Failed' },
                      { value: 'passed', label: 'Passed' },
                      { value: 'all', label: 'All' },
                    ]}
                  />
                )}
                {templates.length > 1 && (
                  <select
                    value={template}
                    onChange={(e) => setTemplate(e.target.value)}
                    className="rounded-[8px] border border-field bg-page px-2.5 py-1 text-[12px] text-data"
                  >
                    <option value="">All templates</option>
                    {templates.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                )}
                {visible.length !== rows.length && (
                  <span className="text-[12px] text-muted">
                    {visible.length} of {rows.length}
                  </span>
                )}
              </div>
              {visible.length === 0 ? (
                <EmptyState>Nothing matches this filter.</EmptyState>
              ) : (
                <RuleTable rows={visible} />
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}

/** When the formula section is empty, say why — never an implied green pass. */
function FormulaEmpty({ formula }: { formula: FormulaSummary | null }) {
  if (!formula) {
    return <EmptyState>Formula validation has not run for this run.</EmptyState>
  }
  if (formula.status === 'executed' && (formula.evaluated ?? 0) === 0) {
    return (
      <div className="rounded-[12px] border border-card border-l-2 border-l-red bg-canvas px-5 py-4">
        <p className="text-[13px] font-semibold text-red">
          Formula validation completed but evaluated 0 rules
        </p>
        <p className="mt-1 text-[12px] text-sub">
          A taxonomy package and rules apply to this run, so zero evaluations is
          treated as a failure, not a pass. {formula.note}
        </p>
      </div>
    )
  }
  return (
    <div className="rounded-[12px] border border-card bg-canvas px-5 py-4">
      <p className="text-[13px] text-data">Formula validation did not run</p>
      {formula.note && (
        <p className="mt-1 text-[12px] text-sub">{formula.note}</p>
      )}
    </div>
  )
}

export default function RunValidation() {
  const ctx = useRun()
  const { detail } = ctx
  const rows = detail.rule_register
  const report = detail.files.find((f) => f.role === 'validation_report')

  const families = useMemo(() => {
    const f: Record<Family, RegisterRow[]> = {
      formula: [],
      structural: [],
      informational: [],
    }
    for (const r of rows) f[familyOf(r)].push(r)
    return f
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

      {/* Per-section summary — the verdict, by family. */}
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-[13px] text-sub">
        <span>{countsLine('Formula', families.formula)}</span>
        <span>{countsLine('Structural', families.structural)}</span>
        <span>
          Informational: {families.informational.length}
        </span>
      </div>

      {detail.run.rule_scope && (
        <p className="text-[13px] text-sub">
          {detail.run.rule_scope.taxonomy_version &&
            `Taxonomy ${detail.run.rule_scope.taxonomy_version} — `}
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
          {/* Formula validations — the headline, open by default. Never green
              when empty. */}
          <Section
            label="Formula"
            title="Formula validations"
            rows={families.formula}
            defaultOpen
            emptyContent={<FormulaEmpty formula={detail.formula_summary} />}
          />

          {/* Filing & structural checks — collapsed by default. */}
          <Section
            label="Structural"
            title="Filing & structural checks"
            rows={families.structural}
            defaultOpen={false}
          />

          {/* Informational — collapsed by default. */}
          <Section
            label="Informational"
            title="Informational"
            rows={families.informational}
            defaultOpen={false}
            showResultFilter={false}
          />
        </div>
      )}
    </section>
  )
}
