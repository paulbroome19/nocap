import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getSnapshot, type Snapshot } from '../api/snapshots'
import {
  downloadRunFile,
  getConfig,
  getEntity,
  getRunDetail,
  getRunFacts,
  type CheckResult,
  type Entity,
  type FactRow,
  type Finding,
  type FormulaSummary,
  type RunDetail as RunDetailT,
  type RunFile,
  type WorkflowConfig,
} from '../api/workflows'
import SeverityBadge from '../components/SeverityBadge'
import { Breadcrumb, Card, ErrorText, Skeleton } from '../components/ui'

// --- helpers ---------------------------------------------------------------

function phaseGroup(phase: string): 'structural' | 'formula' {
  return phase === 'formula' ? 'formula' : 'structural'
}

function findingLocation(f: Finding): string {
  const parts: string[] = []
  if (f.file) {
    let loc = f.file
    if (f.sheet) loc += ` · ${f.sheet}`
    if (f.row != null) loc += ` · row ${f.row}`
    parts.push(loc)
  }
  const cell = [
    f.template_code,
    f.row_code ? `r${f.row_code}` : null,
    f.column_code ? `c${f.column_code}` : null,
  ]
    .filter(Boolean)
    .join(' ')
  if (cell) parts.push(cell)
  return parts.join('  ·  ') || '—'
}

type Counts = { error: number; warning: number; info: number }
function countBy(findings: Finding[]): Counts {
  return {
    error: findings.filter((f) => f.severity === 'error').length,
    warning: findings.filter((f) => f.severity === 'warning').length,
    info: findings.filter((f) => f.severity === 'info').length,
  }
}

// --- state banner ----------------------------------------------------------

function StateBanner({ status, error }: { status: string; error: string | null }) {
  const map: Record<string, { cls: string; dot: string; label: string }> = {
    generated: {
      cls: 'border-emerald-200 bg-emerald-50 text-emerald-900',
      dot: 'bg-emerald-500',
      label: 'Generated — submittable',
    },
    formula_validation_running: {
      cls: 'border-amber-200 bg-amber-50 text-amber-900',
      dot: 'bg-amber-500 animate-pulse',
      label: 'Formula validation running',
    },
    running: {
      cls: 'border-amber-200 bg-amber-50 text-amber-900',
      dot: 'bg-amber-500 animate-pulse',
      label: 'Running',
    },
    failed_validation: {
      cls: 'border-red-200 bg-red-50 text-red-900',
      dot: 'bg-red-500',
      label: 'Failed validation — not submittable',
    },
    failed: {
      cls: 'border-red-200 bg-red-50 text-red-900',
      dot: 'bg-red-500',
      label: 'Run failed',
    },
  }
  const s = map[status] ?? {
    cls: 'border-slate-200 bg-slate-50 text-slate-700',
    dot: 'bg-slate-400',
    label: status,
  }
  return (
    <div className={`flex items-center gap-3 rounded-lg border px-4 py-3 ${s.cls}`}>
      <span className={`h-2.5 w-2.5 rounded-full ${s.dot}`} />
      <span className="text-sm font-semibold">{s.label}</span>
      {status === 'failed' && error && (
        <span className="truncate text-xs opacity-80">— {error}</span>
      )}
    </div>
  )
}

// --- checks executed -------------------------------------------------------

const CHECK_STATUS: Record<string, string> = {
  pass: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20',
  warning: 'bg-amber-50 text-amber-700 ring-amber-600/20',
  fail: 'bg-red-50 text-red-700 ring-red-600/20',
  note: 'bg-sky-50 text-sky-700 ring-sky-600/20',
}

function ChecksExecuted({
  checks,
  formula,
}: {
  checks: CheckResult[]
  formula: FormulaSummary | null
}) {
  return (
    <div className="space-y-4">
      <Card className="overflow-hidden">
        <div className="border-b border-slate-200 px-5 py-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
          Structural checks executed
        </div>
        <table className="w-full text-sm">
          <tbody>
            {checks.map((c) => (
              <tr key={c.key} className="border-b border-slate-100 last:border-0">
                <td className="px-5 py-2.5 text-slate-700">{c.label}</td>
                <td className="px-5 py-2.5">
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium capitalize ring-1 ring-inset ${
                      CHECK_STATUS[c.status] ?? CHECK_STATUS.note
                    }`}
                  >
                    {c.status}
                  </span>
                </td>
                <td className="px-5 py-2.5 text-right font-mono text-xs text-slate-400">
                  {c.errors}E / {c.warnings}W / {c.infos}I
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card className="p-5">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
          Formula validation
        </div>
        <FormulaBlock formula={formula} />
      </Card>
    </div>
  )
}

function FormulaBlock({ formula }: { formula: FormulaSummary | null }) {
  if (!formula || formula.status === 'not_run') {
    return <p className="text-sm text-slate-400">Has not run for this run.</p>
  }
  if (formula.status === 'unavailable') {
    return (
      <p className="text-sm text-slate-600">
        Not run — {formula.note ?? 'unavailable'}.
      </p>
    )
  }
  return (
    <div className="space-y-2 text-sm">
      <p className="text-slate-700">
        Executed —{' '}
        <span className="font-medium">{formula.unsatisfied}</span> rule
        {formula.unsatisfied === 1 ? '' : 's'} unsatisfied.
      </p>
      {formula.unsatisfied_rule_ids.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {formula.unsatisfied_rule_ids.map((r) => (
            <span
              key={r}
              className="rounded bg-red-50 px-1.5 py-0.5 font-mono text-xs text-red-700"
            >
              {r}
            </span>
          ))}
        </div>
      )}
      {formula.deactivated.length > 0 && (
        <p className="text-xs text-slate-400">
          Deactivated rules excluded:{' '}
          <span className="font-mono">{formula.deactivated.join(', ')}</span>
        </p>
      )}
    </div>
  )
}

// --- findings detail -------------------------------------------------------

function SummaryCard({ title, counts }: { title: string; counts: Counts }) {
  const items: [string, number, string][] = [
    ['errors', counts.error, 'text-red-600'],
    ['warnings', counts.warning, 'text-amber-600'],
    ['info', counts.info, 'text-sky-600'],
  ]
  return (
    <Card className="p-4">
      <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">
        {title}
      </div>
      <div className="mt-2 flex gap-5">
        {items.map(([label, n, cls]) => (
          <div key={label}>
            <span className={`font-mono text-xl font-semibold ${n ? cls : 'text-slate-300'}`}>
              {n}
            </span>
            <span className="ml-1 text-xs text-slate-400">{label}</span>
          </div>
        ))}
      </div>
    </Card>
  )
}

function FindingsDetail({ findings }: { findings: Finding[] }) {
  const [severity, setSeverity] = useState<'all' | 'error' | 'warning' | 'info'>(
    'all',
  )
  const [phase, setPhase] = useState<'all' | 'structural' | 'formula'>('all')
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())

  const structural = findings.filter((f) => phaseGroup(f.phase) === 'structural')
  const formula = findings.filter((f) => phaseGroup(f.phase) === 'formula')

  const filtered = findings.filter(
    (f) =>
      (severity === 'all' || f.severity === severity) &&
      (phase === 'all' || phaseGroup(f.phase) === phase),
  )

  const groups = new Map<string, Finding[]>()
  for (const f of filtered) {
    const key = f.template_code ?? 'General'
    const arr = groups.get(key)
    if (arr) arr.push(f)
    else groups.set(key, [f])
  }

  const chip = (active: boolean, onClick: () => void, label: string) => (
    <button
      key={label}
      type="button"
      onClick={onClick}
      className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
        active
          ? 'bg-slate-900 text-white'
          : 'bg-white text-slate-600 ring-1 ring-inset ring-slate-200 hover:bg-slate-50'
      }`}
    >
      {label}
    </button>
  )

  if (findings.length === 0) {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-6">
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-100 text-emerald-700">
          ✓
        </span>
        <div className="text-sm font-semibold text-emerald-900">
          0 errors — all checks passed
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="grid gap-3 sm:grid-cols-2">
        <SummaryCard title="Structural" counts={countBy(structural)} />
        <SummaryCard title="Formula" counts={countBy(formula)} />
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <span className="text-xs text-slate-400">Severity</span>
        {chip(severity === 'all', () => setSeverity('all'), 'All')}
        {chip(severity === 'error', () => setSeverity('error'), 'Errors')}
        {chip(severity === 'warning', () => setSeverity('warning'), 'Warnings')}
        {chip(severity === 'info', () => setSeverity('info'), 'Info')}
        <span className="ml-3 text-xs text-slate-400">Phase</span>
        {chip(phase === 'all', () => setPhase('all'), 'All')}
        {chip(phase === 'structural', () => setPhase('structural'), 'Structural')}
        {chip(phase === 'formula', () => setPhase('formula'), 'Formula')}
      </div>

      <div className="mt-3 space-y-2">
        {[...groups.entries()].map(([template, group]) => {
          const isCollapsed = collapsed.has(template)
          return (
            <Card key={template} className="overflow-hidden">
              <button
                type="button"
                onClick={() =>
                  setCollapsed((prev) => {
                    const next = new Set(prev)
                    if (next.has(template)) next.delete(template)
                    else next.add(template)
                    return next
                  })
                }
                className="flex w-full items-center justify-between bg-slate-50 px-4 py-2 text-left"
              >
                <span className="font-mono text-xs font-medium text-slate-700">
                  {template}
                </span>
                <span className="text-xs text-slate-400">
                  {group.length} · {isCollapsed ? '▸' : '▾'}
                </span>
              </button>
              {!isCollapsed && (
                <table className="w-full text-sm">
                  <tbody>
                    {group.map((f) => (
                      <tr key={f.id} className="border-t border-slate-100 align-top">
                        <td className="px-4 py-2.5">
                          <SeverityBadge severity={f.severity} />
                        </td>
                        <td className="px-2 py-2.5">
                          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-500">
                            {phaseGroup(f.phase)}
                          </span>
                        </td>
                        <td className="whitespace-nowrap px-2 py-2.5 font-mono text-xs text-slate-600">
                          {f.code}
                        </td>
                        <td className="px-2 py-2.5 text-slate-700">
                          {f.message}
                          <div className="mt-0.5 font-mono text-[11px] text-slate-400">
                            {findingLocation(f)}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>
          )
        })}
        {groups.size === 0 && (
          <p className="py-6 text-center text-sm text-slate-400">
            No findings match the filter.
          </p>
        )}
      </div>
    </div>
  )
}

// --- input data ------------------------------------------------------------

function InputData({ detail }: { detail: RunDetailT }) {
  const { run, filing_indicators } = detail
  const [facts, setFacts] = useState<FactRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getRunFacts(run.id)
      .then(setFacts)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [run.id])

  const params: [string, string][] = [
    ['entityID', `${run.entity_lei}.${run.entity_scope}`],
    ['refPeriod', run.reference_date],
    ['baseCurrency', run.base_currency],
    ['decimals', String(run.decimals)],
  ]

  // Group facts by template.
  const groups = new Map<string, FactRow[]>()
  for (const f of facts ?? []) {
    const arr = groups.get(f.template_code)
    if (arr) arr.push(f)
    else groups.set(f.template_code, [f])
  }

  return (
    <div className="space-y-6">
      {/* Derived parameters */}
      <div>
        <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
          Derived parameters
        </div>
        <dl className="grid grid-cols-2 gap-x-8 gap-y-1 text-sm sm:grid-cols-4">
          {params.map(([k, v]) => (
            <div key={k}>
              <dt className="text-xs text-slate-400">{k}</dt>
              <dd className="font-mono text-xs text-slate-700">{v}</dd>
            </div>
          ))}
        </dl>
      </div>

      {/* Filing-indicator outcomes */}
      {filing_indicators && filing_indicators.length > 0 && (
        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
            Filing indicators
          </div>
          <Card className="overflow-x-auto">
            <table className="w-full text-sm">
              <tbody>
                {filing_indicators.map((fi) => (
                  <tr
                    key={fi.template_code}
                    className="border-b border-slate-100 last:border-0"
                  >
                    <td className="px-4 py-1.5 font-mono text-xs text-slate-700">
                      {fi.template_code}
                    </td>
                    <td className="px-4 py-1.5">
                      <span
                        className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${
                          fi.reported
                            ? 'bg-emerald-50 text-emerald-700'
                            : 'bg-slate-100 text-slate-500'
                        }`}
                      >
                        {fi.reported ? 'true' : 'false'}
                      </span>
                    </td>
                    <td className="px-4 py-1.5 text-right text-[11px] text-slate-400">
                      {fi.source}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      )}

      {/* Ingested facts, grouped by template */}
      <div>
        <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
          Ingested facts{' '}
          <span className="font-normal normal-case text-slate-400">
            ({detail.fact_count})
          </span>
        </div>
        <ErrorText>{error}</ErrorText>
        {facts === null && !error ? (
          <Skeleton className="h-24" />
        ) : facts && facts.length === 0 ? (
          <p className="text-sm text-slate-400">No facts ingested.</p>
        ) : (
          <div className="space-y-2">
            {[...groups.entries()].map(([template, rows]) => (
              <Card key={template} className="overflow-hidden">
                <div className="flex items-center justify-between bg-slate-50 px-4 py-2">
                  <span className="font-mono text-xs font-medium text-slate-700">
                    {template}
                  </span>
                  <span className="text-xs text-slate-400">{rows.length}</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-t border-slate-100 text-left text-xs font-medium text-slate-400">
                        <th className="px-4 py-2">Row</th>
                        <th className="px-4 py-2">Column</th>
                        <th className="px-4 py-2">Value</th>
                        <th className="px-4 py-2">Source row</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r, i) => (
                        <tr
                          key={i}
                          className="border-t border-slate-100 font-mono text-xs text-slate-600"
                        >
                          <td className="px-4 py-1.5">{r.row_code}</td>
                          <td className="px-4 py-1.5">{r.column_code}</td>
                          <td className="px-4 py-1.5 text-slate-800">{r.value}</td>
                          <td className="px-4 py-1.5 text-slate-400">
                            {r.source_row ?? '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// --- page ------------------------------------------------------------------

function Chip({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white px-2.5 py-1">
      <div className="text-[10px] font-medium uppercase tracking-wider text-slate-400">
        {label}
      </div>
      <div className="font-mono text-xs text-slate-700">{value || '—'}</div>
    </div>
  )
}

export default function RunDetail() {
  const { runId } = useParams()
  const id = Number(runId)
  const [detail, setDetail] = useState<RunDetailT | null>(null)
  const [config, setConfig] = useState<WorkflowConfig | null>(null)
  const [entity, setEntity] = useState<Entity | null>(null)
  const [release, setRelease] = useState<Snapshot | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [downloadError, setDownloadError] = useState<string | null>(null)
  const [tab, setTab] = useState<'report' | 'input'>('report')

  const load = useCallback(() => {
    getRunDetail(id)
      .then((d) => {
        setDetail(d)
        getConfig(d.run.workflow_id).then(setConfig)
        if (d.run.entity_id) getEntity(d.run.entity_id).then(setEntity).catch(() => {})
        getSnapshot(d.run.snapshot_id).then(setRelease).catch(() => {})
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  const inProgress =
    detail?.run.status === 'running' ||
    detail?.run.status === 'formula_validation_running'
  useEffect(() => {
    if (!inProgress) return
    const t = setInterval(load, 1500)
    return () => clearInterval(t)
  }, [inProgress, load])

  async function handleDownload(f: RunFile) {
    setDownloadError(null)
    try {
      await downloadRunFile(f.id, f.filename)
    } catch (e) {
      setDownloadError(
        `Could not download ${f.filename}: ${
          e instanceof Error ? e.message : String(e)
        }`,
      )
      load()
    }
  }

  if (error) return <ErrorText>{error}</ErrorText>
  if (!detail)
    return (
      <div className="space-y-4">
        <Skeleton className="h-6 w-64" />
        <Skeleton className="h-24" />
        <Skeleton className="h-16" />
      </div>
    )

  const { run, files } = detail
  const pkg = files.find((f) => f.role === 'package_output')
  const report = files.find((f) => f.role === 'validation_report')
  const category = config?.category ?? 'Reporting'
  const entityName = entity?.name ?? run.entity_lei

  const tabBtn = (key: 'report' | 'input', label: string) => (
    <button
      type="button"
      onClick={() => setTab(key)}
      className={`border-b-2 px-1 pb-2 text-sm font-medium transition-colors ${
        tab === key
          ? 'border-slate-900 text-slate-900'
          : 'border-transparent text-slate-400 hover:text-slate-600'
      }`}
    >
      {label}
    </button>
  )

  return (
    <section className="space-y-6">
      <Breadcrumb
        items={[
          { label: 'Reporting', to: '/reporting' },
          { label: category, to: `/reporting/${encodeURIComponent(category)}` },
          {
            label: config?.name ?? 'Suite',
            to: `/reporting/suites/${run.workflow_id}`,
          },
          { label: `Run #${run.id}` },
        ]}
      />

      {/* Identity header */}
      <Card className="p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold tracking-tight text-slate-900">
              {config?.name ?? 'Suite'}
            </h1>
            <div className="mt-1 text-sm text-slate-600">
              {entityName}
              <span className="mx-2 text-slate-300">·</span>
              <span className="text-slate-500">{run.reference_date}</span>
            </div>
          </div>
          <div className="text-right">
            <div className="text-[10px] font-medium uppercase tracking-wider text-slate-400">
              Taxonomy
            </div>
            <div className="font-mono text-sm text-slate-800">
              {release?.version_label ?? `#${run.release_id}`}
            </div>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Chip label="Snapshot" value={run.snapshot_key ?? ''} />
          <Chip label="Adjusted" value={run.adjusted_key ?? ''} />
          <Chip label="Version" value={run.version_key ?? ''} />
        </div>
      </Card>

      <StateBanner status={run.status} error={run.error} />

      {/* One clear package download */}
      {pkg && (
        <div className="flex items-center gap-3">
          {pkg.available ? (
            <button
              type="button"
              onClick={() => void handleDownload(pkg)}
              className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
            >
              Download submission package
            </button>
          ) : (
            <span className="rounded-md bg-slate-100 px-4 py-2 text-sm font-medium text-slate-400">
              Package unavailable
            </span>
          )}
          <span className="truncate font-mono text-xs text-slate-400">
            {pkg.filename}
          </span>
        </div>
      )}

      {downloadError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {downloadError}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-6 border-b border-slate-200">
        {tabBtn('report', 'Validation report')}
        {tabBtn('input', 'Input data')}
      </div>

      {tab === 'report' ? (
        <div className="space-y-6">
          {report && report.available && (
            <button
              type="button"
              onClick={() => void handleDownload(report)}
              className="text-xs text-slate-500 underline hover:text-slate-900"
            >
              Download full report (HTML)
            </button>
          )}
          <ChecksExecuted
            checks={detail.structural_checks}
            formula={detail.formula_summary}
          />
          <FindingsDetail findings={detail.findings} />
        </div>
      ) : (
        <InputData detail={detail} />
      )}
    </section>
  )
}
