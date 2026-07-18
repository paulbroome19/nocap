import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getSnapshot, type Snapshot } from '../api/snapshots'
import {
  downloadRunFile,
  getConfig,
  getEntity,
  getRunDetail,
  getRunFacts,
  type Entity,
  type FactRow,
  type FormulaSummary,
  type RegisterRow,
  type RunDetail as RunDetailT,
  type RunFile,
  type WorkflowConfig,
} from '../api/workflows'
import { Breadcrumb, Card, ErrorText, Skeleton } from '../components/ui'
import { formatDate } from '../lib/format'

// --- shared bits -----------------------------------------------------------

function Stage({
  n,
  title,
  action,
  children,
}: {
  n: number
  title: string
  action?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <section>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2.5 text-sm font-semibold text-slate-900">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-slate-900 font-mono text-[11px] text-white">
            {n}
          </span>
          {title}
        </h2>
        {action}
      </div>
      {children}
    </section>
  )
}

function StateBanner({ status, error }: { status: string; error: string | null }) {
  const map: Record<string, { cls: string; dot: string; label: string }> = {
    generated: {
      cls: 'border-emerald-200 bg-emerald-50 text-emerald-900',
      dot: 'bg-emerald-500', label: 'Successful — submittable',
    },
    formula_validation_running: {
      cls: 'border-amber-200 bg-amber-50 text-amber-900',
      dot: 'bg-amber-500 animate-pulse', label: 'Validating (formula rules)',
    },
    running: {
      cls: 'border-amber-200 bg-amber-50 text-amber-900',
      dot: 'bg-amber-500 animate-pulse', label: 'Running',
    },
    failed_validation: {
      cls: 'border-red-200 bg-red-50 text-red-900',
      dot: 'bg-red-500', label: 'Failed validation — not submittable',
    },
    failed: {
      cls: 'border-red-200 bg-red-50 text-red-900',
      dot: 'bg-red-500', label: 'Run failed',
    },
  }
  const s = map[status] ?? {
    cls: 'border-slate-200 bg-slate-50 text-slate-700',
    dot: 'bg-slate-400', label: status,
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

function Chip({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white px-2.5 py-1">
      <div className="text-[10px] font-medium uppercase tracking-wider text-slate-400">
        {label}
      </div>
      <div className="font-mono text-xs text-slate-700">
        {value || <span className="text-slate-300">·</span>}
      </div>
    </div>
  )
}

// --- stage 1: input data ---------------------------------------------------

function InputData({ runId, factCount }: { runId: number; factCount: number }) {
  const [facts, setFacts] = useState<FactRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getRunFacts(runId)
      .then(setFacts)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [runId])

  const groups = new Map<string, FactRow[]>()
  for (const f of facts ?? []) {
    const arr = groups.get(f.template_code)
    if (arr) arr.push(f)
    else groups.set(f.template_code, [f])
  }

  return (
    <div>
      <ErrorText>{error}</ErrorText>
      {facts === null && !error ? (
        <Skeleton className="h-24" />
      ) : facts && facts.length === 0 ? (
        <p className="text-sm text-slate-400">No facts ingested.</p>
      ) : (
        <div className="space-y-2">
          <p className="text-xs text-slate-400">{factCount} facts</p>
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
  )
}

// --- stage 2: filing indicators --------------------------------------------

function FilingIndicators({ detail }: { detail: RunDetailT }) {
  const fis = detail.filing_indicators
  if (!fis || fis.length === 0) {
    return <p className="text-sm text-slate-400">Not available.</p>
  }
  return (
    <Card className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left text-xs font-medium text-slate-500">
            <th className="px-4 py-2.5">Template</th>
            <th className="px-4 py-2.5">Filed</th>
          </tr>
        </thead>
        <tbody>
          {fis.map((fi) => (
            <tr
              key={fi.template_code}
              className="border-b border-slate-100 last:border-0"
            >
              <td className="px-4 py-2 font-mono text-xs text-slate-700">
                {fi.template_code}
              </td>
              <td className="px-4 py-2">
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
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}

// --- stage 3: validation report (rule register) ----------------------------

const RESULT_STYLE: Record<string, string> = {
  PASSED: 'bg-emerald-50 text-emerald-700',
  FAILED: 'bg-red-50 text-red-700',
  WARNING: 'bg-amber-50 text-amber-700',
  NOTE: 'bg-sky-50 text-sky-700',
}

function FormulaNote({ formula }: { formula: FormulaSummary | null }) {
  if (!formula || formula.status === 'not_run') {
    return (
      <p className="text-xs text-slate-400">Formula validation has not run.</p>
    )
  }
  if (formula.status === 'unavailable') {
    return (
      <p className="text-xs text-slate-500">
        Formula validation not run — {formula.note ?? 'unavailable'}.
      </p>
    )
  }
  return (
    <p className="text-xs text-slate-500">
      Formula validation executed — {formula.loaded ?? 0} rules loaded,{' '}
      {formula.evaluated ?? 0} evaluated ({formula.satisfied ?? 0} satisfied,{' '}
      {formula.unsatisfied} unsatisfied).
      {formula.deactivated.length > 0 && (
        <>
          {' '}
          Deactivated rules excluded:{' '}
          <span className="font-mono">{formula.deactivated.join(', ')}</span>.
        </>
      )}
    </p>
  )
}

function Register({
  rows,
  formula,
}: {
  rows: RegisterRow[]
  formula: FormulaSummary | null
}) {
  const [result, setResult] = useState<string>('all')
  const [source, setSource] = useState<string>('all')
  const [template, setTemplate] = useState<string>('all')

  const templates = [...new Set(rows.map((r) => r.template).filter(Boolean))]

  const filtered = rows.filter(
    (r) =>
      (result === 'all' || r.result === result) &&
      (source === 'all' || r.source === source) &&
      (template === 'all' || r.template === template),
  )

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

  return (
    <div>
      <div className="mb-3">
        <FormulaNote formula={formula} />
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="text-xs text-slate-400">Result</span>
        {chip(result === 'all', () => setResult('all'), 'All')}
        {['PASSED', 'FAILED', 'WARNING', 'NOTE'].map((r) =>
          chip(result === r, () => setResult(r), r[0] + r.slice(1).toLowerCase()),
        )}
        <span className="ml-3 text-xs text-slate-400">Source</span>
        {chip(source === 'all', () => setSource('all'), 'All')}
        {chip(source === 'structural', () => setSource('structural'), 'Structural')}
        {chip(source === 'formula', () => setSource('formula'), 'Formula')}
        {templates.length > 0 && (
          <select
            value={template}
            onChange={(e) => setTemplate(e.target.value)}
            className="ml-3 rounded-md border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700"
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

      <Card className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs font-medium text-slate-500">
              <th className="px-4 py-2.5">ID</th>
              <th className="px-4 py-2.5">Rule</th>
              <th className="px-4 py-2.5">Data evaluated</th>
              <th className="px-4 py-2.5">Result</th>
              <th className="px-4 py-2.5">Detail</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r, i) => (
              <tr key={i} className="border-b border-slate-100 align-top last:border-0">
                <td className="whitespace-nowrap px-4 py-2 font-mono text-xs text-slate-700">
                  {r.id}
                </td>
                <td className="px-4 py-2 text-slate-700">{r.rule}</td>
                <td className="px-4 py-2 font-mono text-xs text-slate-500">
                  {r.data_evaluated || (
                    <span className="text-slate-300">·</span>
                  )}
                </td>
                <td className="px-4 py-2">
                  <span
                    className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${
                      RESULT_STYLE[r.result] ?? RESULT_STYLE.NOTE
                    }`}
                  >
                    {r.result}
                  </span>
                </td>
                <td className="px-4 py-2 text-xs text-slate-500">{r.detail}</td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-sm text-slate-400">
                  No rules match the filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  )
}

// --- page ------------------------------------------------------------------

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
        <Skeleton className="h-24" />
        <Skeleton className="h-16" />
      </div>
    )

  const { run, files } = detail
  const pkg = files.find((f) => f.role === 'package_output')
  const report = files.find((f) => f.role === 'validation_report')
  const category = config?.category ?? 'Reporting'
  const entityName = entity?.name ?? run.entity_lei

  return (
    <section className="space-y-8">
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
              <span className="text-slate-500">
                {formatDate(run.reference_date)}
              </span>
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
          <Chip label="Snapshot" value={run.snapshot_key} />
          <Chip label="Adjusted" value={run.adjusted_key} />
          <Chip label="Version" value={run.version_key} />
        </div>
      </Card>

      <StateBanner status={run.status} error={run.error} />

      {downloadError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {downloadError}
        </div>
      )}

      <Stage n={1} title="Input Data">
        <InputData runId={run.id} factCount={detail.fact_count} />
      </Stage>

      <Stage n={2} title="Filing Indicators">
        <FilingIndicators detail={detail} />
      </Stage>

      <Stage
        n={3}
        title="Validation Report"
        action={
          report && report.available ? (
            <button
              type="button"
              onClick={() => void handleDownload(report)}
              className="text-xs text-slate-500 underline hover:text-slate-900"
            >
              Download report (HTML)
            </button>
          ) : undefined
        }
      >
        <Register rows={detail.rule_register} formula={detail.formula_summary} />
      </Stage>

      <Stage n={4} title="Download">
        {pkg ? (
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
        ) : (
          <p className="text-sm text-slate-400">No package generated.</p>
        )}
      </Stage>
    </section>
  )
}
