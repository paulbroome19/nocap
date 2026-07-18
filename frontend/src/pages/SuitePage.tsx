import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { listSnapshots, type Snapshot } from '../api/snapshots'
import {
  attachFactFile,
  createRun,
  executeRun,
  getConfig,
  listEntities,
  runHistory,
  type Entity,
  type Run,
  type WorkflowConfig,
} from '../api/workflows'
import RunStatusBadge from '../components/RunStatusBadge'
import UploadZone from '../components/UploadZone'
import {
  Card,
  ErrorText,
  PageHeader,
  Select,
  fieldClass,
  primaryBtn,
} from '../components/ui'
import { formatDate, formatTime } from '../lib/format'

/** Empty instance key → a subtle middot; alignment preserved. */
function keyCell(value: string | null) {
  return value ? value : <span className="text-slate-300">·</span>
}

/**
 * Compact capability indicator for the release picker. Options are text-only,
 * so this is a terse trailing string — ready releases always resolve/generate,
 * so it mostly conveys formula validation, the rule register, and verified
 * entry points.
 */
function releaseCaps(s: Snapshot): string {
  const c = s.capabilities
  if (!c) return ''
  const on = [
    c.generate && c.verified_entry_points ? 'verified' : null,
    c.formula_validate ? 'formula' : null,
    c.rule_register ? 'register' : null,
  ].filter(Boolean)
  return on.length ? `  ·  ${on.join(' · ')}` : ''
}

export default function SuitePage() {
  const { workflowId } = useParams()
  const id = Number(workflowId)
  const navigate = useNavigate()

  const [config, setConfig] = useState<WorkflowConfig | null>(null)
  const [releases, setReleases] = useState<Snapshot[]>([])
  const [entities, setEntities] = useState<Entity[]>([])
  const [runs, setRuns] = useState<Run[]>([])

  // Form state
  const [reportingDate, setReportingDate] = useState('')
  const [entityId, setEntityId] = useState<number | ''>('')
  const [snapshotKey, setSnapshotKey] = useState('')
  const [adjustedKey, setAdjustedKey] = useState('')
  const [versionKey, setVersionKey] = useState('')
  const [releaseId, setReleaseId] = useState<number | ''>('')
  const [factFile, setFactFile] = useState<File | null>(null)

  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedDate, setSelectedDate] = useState<string | null>(null)

  const loadRuns = useCallback(() => {
    if (id) runHistory(id).then(setRuns).catch(() => setRuns([]))
  }, [id])

  useEffect(() => {
    getConfig(id).then(setConfig)
    listSnapshots().then((s) => setReleases(s.filter((x) => x.status === 'ready')))
    listEntities().then(setEntities)
    loadRuns()
  }, [id, loadRuns])

  // Runs grouped by reporting date, newest date first.
  const byDate = useMemo(() => {
    const m = new Map<string, Run[]>()
    for (const r of runs) {
      const arr = m.get(r.reference_date)
      if (arr) arr.push(r)
      else m.set(r.reference_date, [r])
    }
    return m
  }, [runs])
  const dates = useMemo(
    () => [...byDate.keys()].sort((a, b) => b.localeCompare(a)),
    [byDate],
  )
  useEffect(() => {
    if (dates.length && (selectedDate === null || !byDate.has(selectedDate))) {
      setSelectedDate(dates[0])
    }
  }, [dates, byDate, selectedDate])

  const ready =
    reportingDate !== '' &&
    entityId !== '' &&
    releaseId !== '' &&
    factFile !== null &&
    busy === null

  async function handleRun() {
    if (entityId === '' || releaseId === '' || !factFile) return
    setError(null)
    try {
      setBusy('Creating run…')
      const run = await createRun({
        workflow_id: id,
        snapshot_id: releaseId,
        reference_date: reportingDate,
        entity_id: entityId,
        snapshot_key: snapshotKey || undefined,
        adjusted_key: adjustedKey || undefined,
        version_key: versionKey || undefined,
      })
      setBusy('Uploading facts…')
      await attachFactFile(run.id, factFile)
      setBusy('Generating & validating…')
      await executeRun(run.id)
      navigate(`/reporting/runs/${run.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setBusy(null)
      loadRuns()
    }
  }

  const category = config?.category ?? 'Reporting'
  // Group a date's runs into submission instances (by the three keys); each
  // instance shows its latest execution, with earlier ones counted. Re-executed
  // instances collapse to one row (latest prominent) rather than repeating.
  const instances = useMemo(() => {
    const dateRuns = selectedDate ? (byDate.get(selectedDate) ?? []) : []
    const m = new Map<string, Run[]>()
    for (const r of dateRuns) {
      const sig = `${r.snapshot_key}|${r.adjusted_key}|${r.version_key}`
      const arr = m.get(sig)
      if (arr) arr.push(r)
      else m.set(sig, [r])
    }
    return [...m.values()].map((runs) => {
      const sorted = [...runs].sort((a, b) => b.id - a.id)
      return { latest: sorted[0], count: runs.length }
    })
  }, [byDate, selectedDate])

  return (
    <section>
      <PageHeader
        title={config?.name ?? 'Suite'}
        crumbs={[
          { label: 'Reporting', to: '/reporting' },
          { label: category, to: `/reporting/${encodeURIComponent(category)}` },
          { label: config?.name ?? '' },
        ]}
      />
      <p className="-mt-4 mb-6 font-mono text-xs text-slate-400">
        {config?.module_code}
      </p>

      {/* Run creation */}
      <Card className="p-5">
        {releases.length === 0 ? (
          <p className="text-sm text-amber-700">
            No ready taxonomy releases. Onboard one under Taxonomy Releases first.
          </p>
        ) : (
          <div className="space-y-4">
            {/* Reporting Date + Entity */}
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="flex flex-col gap-1">
                <span className="text-xs font-medium text-slate-600">
                  Reporting Date
                </span>
                <input
                  type="date"
                  className={fieldClass}
                  value={reportingDate}
                  onChange={(e) => setReportingDate(e.target.value)}
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs font-medium text-slate-600">Entity</span>
                <Select
                  value={entityId}
                  onChange={(v) => setEntityId(v === '' ? '' : Number(v))}
                >
                  <option value="">Select…</option>
                  {entities.map((en) => (
                    <option key={en.id} value={en.id}>
                      {en.name} · {en.lei}
                    </option>
                  ))}
                </Select>
              </label>
            </div>

            {/* Instance keys */}
            <div className="rounded-md border border-slate-200 bg-slate-50/60 p-3">
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                Instance keys
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                {(
                  [
                    ['Snapshot', snapshotKey, setSnapshotKey],
                    ['Adjusted', adjustedKey, setAdjustedKey],
                    ['Version', versionKey, setVersionKey],
                  ] as const
                ).map(([label, value, set]) => (
                  <label key={label} className="flex flex-col gap-1">
                    <span className="text-xs font-medium text-slate-600">
                      {label}
                    </span>
                    <input
                      type="text"
                      className={`${fieldClass} font-mono`}
                      value={value}
                      onChange={(e) => set(e.target.value)}
                      placeholder="—"
                    />
                  </label>
                ))}
              </div>
            </div>

            {/* What you're running: taxonomy release + fact file, together */}
            <div className="rounded-md border border-slate-200 bg-slate-50/60 p-3">
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                What you&rsquo;re running
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="flex flex-col gap-1">
                  <span className="text-xs font-medium text-slate-600">
                    Taxonomy Release
                  </span>
                  <Select
                    value={releaseId}
                    onChange={(v) => setReleaseId(v === '' ? '' : Number(v))}
                  >
                    <option value="">Select…</option>
                    {releases.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.version_label} — {s.original_filename}
                        {releaseCaps(s)}
                      </option>
                    ))}
                  </Select>
                </label>
                <div className="flex flex-col gap-1">
                  <span className="text-xs font-medium text-slate-600">
                    Fact file
                  </span>
                  <UploadZone
                    accept=".xlsx"
                    onFile={setFactFile}
                    file={factFile}
                    hint="XLSX"
                    compact
                  />
                </div>
              </div>
            </div>

            <div className="flex items-center gap-3 pt-1">
              <button
                type="button"
                onClick={() => void handleRun()}
                disabled={!ready}
                className={primaryBtn}
              >
                Run
              </button>
              {busy && <span className="text-sm text-slate-500">{busy}</span>}
              <ErrorText>{error}</ErrorText>
            </div>
          </div>
        )}
      </Card>

      {/* History — organised by reporting date, newest first */}
      {dates.length > 0 && (
        <div className="mt-8 flex gap-6">
          {/* Date selector */}
          <div className="w-40 shrink-0">
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              Reporting date
            </div>
            <div className="space-y-1">
              {dates.map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setSelectedDate(d)}
                  className={`flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-left font-mono text-xs transition-colors ${
                    selectedDate === d
                      ? 'bg-slate-900 text-white'
                      : 'text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  {formatDate(d)}
                  <span
                    className={
                      selectedDate === d ? 'text-slate-300' : 'text-slate-400'
                    }
                  >
                    {byDate.get(d)?.length}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Runs for the selected date */}
          <Card className="min-w-0 flex-1 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-[11px] font-medium uppercase tracking-wide text-slate-400">
                  <th className="px-4 py-3 font-medium">Snapshot</th>
                  <th className="px-4 py-3 font-medium">Adjusted</th>
                  <th className="px-4 py-3 font-medium">Version</th>
                  <th className="px-4 py-3 font-medium">Executions</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {instances.map(({ latest, count }) => (
                  <tr
                    key={latest.id}
                    onClick={() => navigate(`/reporting/runs/${latest.id}`)}
                    className="cursor-pointer border-b border-slate-100 transition-colors last:border-0 hover:bg-slate-50"
                  >
                    <td className="px-4 py-3 font-mono text-xs text-slate-600">
                      {keyCell(latest.snapshot_key)}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-600">
                      {keyCell(latest.adjusted_key)}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-600">
                      {keyCell(latest.version_key)}
                    </td>
                    <td className="px-4 py-3">
                      {count > 1 ? (
                        <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium tabular-nums text-slate-600">
                          {count}×
                          <span className="font-mono text-slate-400">
                            {formatTime(latest.created_at)}
                          </span>
                        </span>
                      ) : (
                        <span className="text-xs text-slate-300">1</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <RunStatusBadge status={latest.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      )}
    </section>
  )
}
