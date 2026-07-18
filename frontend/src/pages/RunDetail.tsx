import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getSnapshot, type Snapshot } from '../api/snapshots'
import {
  downloadRunFile,
  getConfig,
  getEntity,
  getRunDetail,
  type Entity,
  type Finding,
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

function formatBytes(n: number | null): string {
  if (n == null) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
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
    <div
      className={`flex items-center gap-3 rounded-lg border px-4 py-3 ${s.cls}`}
    >
      <span className={`h-2.5 w-2.5 rounded-full ${s.dot}`} />
      <span className="text-sm font-semibold">{s.label}</span>
      {status === 'failed' && error && (
        <span className="truncate text-xs opacity-80">— {error}</span>
      )}
    </div>
  )
}

// --- pipeline timeline -----------------------------------------------------

type StepState = 'done' | 'active' | 'error' | 'skipped' | 'pending'

function StepIcon({ state }: { state: StepState }) {
  const base = 'flex h-7 w-7 items-center justify-center rounded-full text-xs'
  if (state === 'done')
    return <span className={`${base} bg-emerald-100 text-emerald-700`}>✓</span>
  if (state === 'error')
    return <span className={`${base} bg-red-100 text-red-700`}>!</span>
  if (state === 'active')
    return (
      <span className={`${base} bg-amber-100 text-amber-700`}>
        <span className="h-2 w-2 animate-pulse rounded-full bg-amber-500" />
      </span>
    )
  return <span className={`${base} bg-slate-100 text-slate-400`}>○</span>
}

function Pipeline({ detail }: { detail: RunDetailT }) {
  const { run, findings, files, fact_count } = detail
  const structural = findings.filter((f) => phaseGroup(f.phase) === 'structural')
  const formula = findings.filter((f) => phaseGroup(f.phase) === 'formula')
  const pkg = files.find((f) => f.role === 'package_output')
  const executed = !['created', 'files_attached'].includes(run.status)

  const sErr = structural.filter((f) => f.severity === 'error').length
  const fErr = formula.filter((f) => f.severity === 'error').length

  const steps: { label: string; sub: string; state: StepState }[] = [
    {
      label: 'Facts ingested',
      sub: `${fact_count} fact${fact_count === 1 ? '' : 's'}`,
      state: executed ? 'done' : 'pending',
    },
    {
      label: 'Structural validation',
      sub: executed ? `${structural.length} findings` : 'pending',
      state: !executed
        ? 'pending'
        : run.status === 'running'
          ? 'active'
          : sErr > 0
            ? 'error'
            : 'done',
    },
    {
      label: 'Package generated',
      sub: pkg ? pkg.filename : 'pending',
      state: pkg ? 'done' : run.status === 'failed' ? 'error' : 'pending',
    },
    {
      label: 'Formula validation',
      sub:
        run.status === 'formula_validation_running'
          ? 'running…'
          : formula.length > 0
            ? `${formula.length} findings`
            : executed
              ? 'not run'
              : 'pending',
      state:
        run.status === 'formula_validation_running'
          ? 'active'
          : formula.length > 0
            ? fErr > 0
              ? 'error'
              : 'done'
            : 'skipped',
    },
  ]

  return (
    <div className="flex items-stretch">
      {steps.map((s, i) => (
        <div key={s.label} className="flex flex-1 items-start">
          <div className="flex min-w-0 flex-col items-center px-2 text-center">
            <StepIcon state={s.state} />
            <div className="mt-2 text-xs font-medium text-slate-700">
              {s.label}
            </div>
            <div className="mt-0.5 max-w-[9rem] truncate font-mono text-[11px] text-slate-400">
              {s.sub}
            </div>
          </div>
          {i < steps.length - 1 && (
            <div className="mt-3.5 h-px flex-1 bg-slate-200" />
          )}
        </div>
      ))}
    </div>
  )
}

// --- findings console ------------------------------------------------------

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

function FindingsConsole({ detail }: { detail: RunDetailT }) {
  const [severity, setSeverity] = useState<'all' | 'error' | 'warning' | 'info'>(
    'all',
  )
  const [phase, setPhase] = useState<'all' | 'structural' | 'formula'>('all')
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())

  const findings = detail.findings
  const structural = findings.filter((f) => phaseGroup(f.phase) === 'structural')
  const formula = findings.filter((f) => phaseGroup(f.phase) === 'formula')

  const filtered = findings.filter(
    (f) =>
      (severity === 'all' || f.severity === severity) &&
      (phase === 'all' || phaseGroup(f.phase) === phase),
  )

  // Group by template code.
  const groups = new Map<string, Finding[]>()
  for (const f of filtered) {
    const key = f.template_code ?? 'General'
    const arr = groups.get(key)
    if (arr) arr.push(f)
    else groups.set(key, [f])
  }

  const clean = findings.length === 0

  const chip = (
    active: boolean,
    onClick: () => void,
    label: string,
  ) => (
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

  return (
    <div>
      <div className="grid gap-3 sm:grid-cols-2">
        <SummaryCard title="Structural" counts={countBy(structural)} />
        <SummaryCard title="Formula" counts={countBy(formula)} />
      </div>

      {clean ? (
        <div className="mt-4 flex items-center gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-6">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-100 text-emerald-700">
            ✓
          </span>
          <div>
            <div className="text-sm font-semibold text-emerald-900">
              0 errors — all checks passed
            </div>
            <div className="text-xs text-emerald-700">
              No validation findings were raised for this run.
            </div>
          </div>
        </div>
      ) : (
        <>
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
                          <tr
                            key={f.id}
                            className="border-t border-slate-100 align-top"
                          >
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
        </>
      )}
    </div>
  )
}

// --- artifacts -------------------------------------------------------------

function ArtifactCard({
  file,
  title,
  onDownload,
}: {
  file: RunFile
  title: string
  onDownload: (f: RunFile) => void
}) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            {title}
          </div>
          <div className="mt-1 truncate font-mono text-xs text-slate-700">
            {file.filename}
          </div>
        </div>
        {file.available ? (
          <button
            type="button"
            onClick={() => onDownload(file)}
            className="shrink-0 rounded-md bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-700"
          >
            Download
          </button>
        ) : (
          <span className="shrink-0 rounded-md bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-400">
            Unavailable
          </span>
        )}
      </div>
      <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
        <dt className="text-slate-400">Size</dt>
        <dd className="font-mono text-slate-600">{formatBytes(file.size_bytes)}</dd>
        <dt className="text-slate-400">SHA-256</dt>
        <dd
          className="truncate font-mono text-slate-500"
          title={file.checksum}
        >
          {file.checksum}
        </dd>
      </dl>
    </Card>
  )
}

// --- inputs panel ----------------------------------------------------------

function InputsPanel({
  detail,
  onDownload,
}: {
  detail: RunDetailT
  onDownload: (f: RunFile) => void
}) {
  const [open, setOpen] = useState(false)
  const { run, files, filing_indicators } = detail
  const factFile = files.find((f) => f.role === 'fact_input')

  const params: [string, string][] = [
    ['entityID', `${run.entity_lei}.${run.entity_scope}`],
    ['refPeriod', run.reference_date],
    ['baseCurrency', run.base_currency],
    ['decimals', String(run.decimals)],
  ]

  return (
    <Card className="overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between px-5 py-3 text-left"
      >
        <span className="text-sm font-semibold text-slate-900">
          Inputs & traceability
        </span>
        <span className="text-xs text-slate-400">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <div className="space-y-6 border-t border-slate-100 px-5 py-4">
          {/* Fact file */}
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
              Fact file
            </div>
            {factFile ? (
              <div className="flex items-center justify-between rounded-md bg-slate-50 px-3 py-2">
                <span className="truncate font-mono text-xs text-slate-700">
                  {factFile.filename}
                </span>
                {factFile.available ? (
                  <button
                    type="button"
                    onClick={() => onDownload(factFile)}
                    className="text-xs text-slate-500 hover:text-slate-800 hover:underline"
                  >
                    download
                  </button>
                ) : (
                  <span className="text-xs text-slate-300">unavailable</span>
                )}
              </div>
            ) : (
              <p className="text-xs text-slate-400">None.</p>
            )}
          </div>

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
          <div>
            <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
              Filing indicators
            </div>
            {filing_indicators && filing_indicators.length > 0 ? (
              <div className="overflow-x-auto rounded-md border border-slate-200">
                <table className="w-full text-sm">
                  <tbody>
                    {filing_indicators.map((fi) => (
                      <tr
                        key={fi.template_code}
                        className="border-b border-slate-100 last:border-0"
                      >
                        <td className="px-3 py-1.5 font-mono text-xs text-slate-700">
                          {fi.template_code}
                        </td>
                        <td className="px-3 py-1.5">
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
                        <td className="px-3 py-1.5 text-right">
                          <span className="text-[11px] text-slate-400">
                            {fi.source === 'declared' ? 'declared' : 'auto'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="text-xs text-slate-400">Not available.</p>
            )}
          </div>
        </div>
      )}
    </Card>
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
        <Skeleton className="h-28" />
        <Skeleton className="h-20" />
      </div>
    )

  const { run, files } = detail
  const outputs = files.filter((f) => f.role === 'package_output')
  const reports = files.filter((f) => f.role === 'validation_report')
  const category = config?.category ?? 'Reporting'
  const entityName = entity?.name ?? run.entity_lei

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
              {entityName}
            </h1>
            <div className="mt-0.5 font-mono text-xs text-slate-400">
              {run.entity_lei}.{run.entity_scope}
            </div>
            <div className="mt-2 text-sm text-slate-600">
              {config?.name ?? 'Suite'}
              <span className="mx-2 text-slate-300">·</span>
              <span className="text-slate-500">{run.reference_date}</span>
            </div>
          </div>
          <div className="text-right text-xs text-slate-500">
            <div className="text-[10px] font-medium uppercase tracking-wider text-slate-400">
              Taxonomy Release
            </div>
            <div className="font-mono text-sm text-slate-800">
              {release?.version_label ?? `#${run.release_id}`}
            </div>
            <div className="mt-1 font-mono text-xs text-slate-400">
              {config?.module_code}
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

      {run.status === 'failed' && run.failure_details && run.failure_details.length > 0 && (
        <Card className="border-red-200 bg-red-50 p-4">
          <ul className="space-y-1 text-xs text-red-700">
            {run.failure_details.slice(0, 20).map((d, i) => (
              <li key={i} className="font-mono">
                {JSON.stringify(d)}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* Pipeline */}
      <Card className="p-5">
        <Pipeline detail={detail} />
      </Card>

      {downloadError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {downloadError}
        </div>
      )}

      {/* Artifacts */}
      {(outputs.length > 0 || reports.length > 0) && (
        <div className="grid gap-3 sm:grid-cols-2">
          {outputs.map((f) => (
            <ArtifactCard
              key={f.id}
              file={f}
              title="Submission package"
              onDownload={handleDownload}
            />
          ))}
          {reports.map((f) => (
            <ArtifactCard
              key={f.id}
              file={f}
              title="Validation report"
              onDownload={handleDownload}
            />
          ))}
        </div>
      )}

      {/* Findings */}
      <FindingsConsole detail={detail} />

      {/* Inputs */}
      <InputsPanel detail={detail} onDownload={handleDownload} />
    </section>
  )
}
