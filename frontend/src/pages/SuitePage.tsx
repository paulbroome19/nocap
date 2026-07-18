import { useCallback, useEffect, useState } from 'react'
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
import {
  Card,
  EmptyState,
  ErrorText,
  Loading,
  PageHeader,
  fieldClass,
  fileInputClass,
  primaryBtn,
} from '../components/ui'

export default function SuitePage() {
  const { workflowId } = useParams()
  const id = Number(workflowId)
  const navigate = useNavigate()

  const [config, setConfig] = useState<WorkflowConfig | null>(null)
  const [releases, setReleases] = useState<Snapshot[]>([])
  const [entities, setEntities] = useState<Entity[]>([])
  const [runs, setRuns] = useState<Run[] | null>(null)

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

  const loadRuns = useCallback(() => {
    if (id) runHistory(id).then(setRuns).catch(() => setRuns([]))
  }, [id])

  useEffect(() => {
    getConfig(id).then(setConfig)
    listSnapshots().then((s) => setReleases(s.filter((x) => x.status === 'ready')))
    listEntities().then(setEntities)
    loadRuns()
  }, [id, loadRuns])

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
  const entityLabel = (e: Entity) => `${e.name} · ${e.lei}`

  return (
    <section>
      <PageHeader
        title={config?.name ?? 'Suite'}
        crumbs={[
          { label: 'Reporting', to: '/reporting' },
          {
            label: category,
            to: `/reporting/${encodeURIComponent(category)}`,
          },
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
            {/* Row 1 — Reporting Date, Entity */}
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
                <select
                  className={fieldClass}
                  value={entityId}
                  onChange={(e) =>
                    setEntityId(e.target.value === '' ? '' : Number(e.target.value))
                  }
                >
                  <option value="">Select…</option>
                  {entities.map((en) => (
                    <option key={en.id} value={en.id}>
                      {entityLabel(en)}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            {/* Row 2 — instance keys */}
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

            {/* Taxonomy release + fact file */}
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="flex flex-col gap-1">
                <span className="text-xs font-medium text-slate-600">
                  Taxonomy Release
                </span>
                <select
                  className={fieldClass}
                  value={releaseId}
                  onChange={(e) =>
                    setReleaseId(e.target.value === '' ? '' : Number(e.target.value))
                  }
                >
                  <option value="">Select…</option>
                  {releases.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.version_label} — {s.original_filename}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs font-medium text-slate-600">
                  Fact file (XLSX)
                </span>
                <input
                  type="file"
                  accept=".xlsx"
                  className={fileInputClass}
                  onChange={(e) => setFactFile(e.target.files?.[0] ?? null)}
                />
              </label>
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

      {/* Run history */}
      <div className="mt-8">
        {runs === null ? (
          <Loading />
        ) : runs.length === 0 ? (
          <EmptyState>No runs yet.</EmptyState>
        ) : (
          <Card className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs font-medium text-slate-500">
                  <th className="px-4 py-3">Run</th>
                  <th className="px-4 py-3">Reporting Date</th>
                  <th className="px-4 py-3">Entity</th>
                  <th className="px-4 py-3">Snapshot</th>
                  <th className="px-4 py-3">Adjusted</th>
                  <th className="px-4 py-3">Version</th>
                  <th className="px-4 py-3">Status</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr
                    key={r.id}
                    onClick={() => navigate(`/reporting/runs/${r.id}`)}
                    className="cursor-pointer border-b border-slate-100 transition-colors last:border-0 hover:bg-slate-50"
                  >
                    <td className="px-4 py-3 font-medium text-slate-900">
                      #{r.id}
                    </td>
                    <td className="px-4 py-3 text-slate-600">{r.reference_date}</td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-500">
                      {r.entity_lei}.{r.entity_scope}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-500">
                      {r.snapshot_key ?? '—'}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-500">
                      {r.adjusted_key ?? '—'}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-500">
                      {r.version_key ?? '—'}
                    </td>
                    <td className="px-4 py-3">
                      <RunStatusBadge status={r.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </div>
    </section>
  )
}
