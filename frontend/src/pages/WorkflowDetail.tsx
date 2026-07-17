import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { listSnapshots, type Snapshot } from '../api/snapshots'
import {
  attachFactFile,
  attachIndicatorsFile,
  createRun,
  executeRun,
  listConfigs,
  runHistory,
  type Run,
  type WorkflowConfig,
} from '../api/workflows'
import RunStatusBadge from '../components/RunStatusBadge'

export default function WorkflowDetail() {
  const { workflowId } = useParams()
  const id = Number(workflowId)
  const navigate = useNavigate()

  const [config, setConfig] = useState<WorkflowConfig | null>(null)
  const [snapshots, setSnapshots] = useState<Snapshot[]>([])
  const [runs, setRuns] = useState<Run[]>([])

  // Form state
  const [snapshotId, setSnapshotId] = useState<number | ''>('')
  const [referenceDate, setReferenceDate] = useState('')
  const [entityLei, setEntityLei] = useState('')
  const [scope, setScope] = useState('CON')
  const [factFile, setFactFile] = useState<File | null>(null)
  const [indicatorsFile, setIndicatorsFile] = useState<File | null>(null)

  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadRuns = useCallback(() => {
    if (id) runHistory(id).then(setRuns).catch(() => {})
  }, [id])

  useEffect(() => {
    listConfigs().then((cs) => setConfig(cs.find((c) => c.id === id) ?? null))
    listSnapshots().then((s) => setSnapshots(s.filter((x) => x.status === 'ready')))
    loadRuns()
  }, [id, loadRuns])

  const ready =
    snapshotId !== '' &&
    referenceDate !== '' &&
    entityLei.trim() !== '' &&
    factFile !== null &&
    indicatorsFile !== null &&
    busy === null

  async function handleRun() {
    if (snapshotId === '' || !factFile || !indicatorsFile) return
    setError(null)
    try {
      setBusy('Creating run…')
      const run = await createRun({
        workflow_id: id,
        snapshot_id: snapshotId,
        reference_date: referenceDate,
        entity_lei: entityLei.trim(),
        entity_scope: scope,
      })
      setBusy('Uploading fact file…')
      await attachFactFile(run.id, factFile)
      setBusy('Uploading indicators / parameters…')
      await attachIndicatorsFile(run.id, indicatorsFile)
      setBusy('Generating package…')
      await executeRun(run.id)
      navigate(`/runs/${run.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setBusy(null)
      loadRuns()
    }
  }

  const field = 'w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none'

  return (
    <section>
      <Link to="/workflows" className="text-xs text-slate-500 hover:text-slate-800">
        ← Workflows
      </Link>
      <h1 className="mt-1 text-2xl font-semibold tracking-tight">
        {config?.name ?? 'Workflow'}
      </h1>
      <p className="mt-1 font-mono text-xs text-slate-400">
        {config?.module_code}
      </p>

      {/* New run */}
      <div className="mt-6 rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="text-sm font-semibold text-slate-900">New run</h2>

        {snapshots.length === 0 ? (
          <p className="mt-3 text-sm text-amber-700">
            No ready snapshots.{' '}
            <Link to="/snapshots" className="underline">
              Upload a DPM release
            </Link>{' '}
            first.
          </p>
        ) : (
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-slate-600">Snapshot</span>
              <select
                className={field}
                value={snapshotId}
                onChange={(e) => setSnapshotId(Number(e.target.value))}
              >
                <option value="">Select…</option>
                {snapshots.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.version_label} — {s.original_filename}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-slate-600">
                Reference date
              </span>
              <input
                type="date"
                className={field}
                value={referenceDate}
                onChange={(e) => setReferenceDate(e.target.value)}
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-slate-600">Entity LEI</span>
              <input
                type="text"
                className={field}
                placeholder="20 alphanumeric chars"
                value={entityLei}
                onChange={(e) => setEntityLei(e.target.value)}
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-slate-600">Scope</span>
              <select
                className={field}
                value={scope}
                onChange={(e) => setScope(e.target.value)}
              >
                <option value="CON">Consolidated (CON)</option>
                <option value="IND">Individual (IND)</option>
              </select>
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-slate-600">Fact file (XLSX)</span>
              <input
                type="file"
                accept=".xlsx"
                className="text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-1.5 file:text-sm file:font-medium hover:file:bg-slate-200"
                onChange={(e) => setFactFile(e.target.files?.[0] ?? null)}
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-slate-600">
                Indicators / parameters (XLSX)
              </span>
              <input
                type="file"
                accept=".xlsx"
                className="text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-1.5 file:text-sm file:font-medium hover:file:bg-slate-200"
                onChange={(e) => setIndicatorsFile(e.target.files?.[0] ?? null)}
              />
            </label>
          </div>
        )}

        {snapshots.length > 0 && (
          <div className="mt-5 flex items-center gap-3">
            <button
              type="button"
              onClick={() => void handleRun()}
              disabled={!ready}
              className="rounded-md bg-slate-900 px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Run
            </button>
            {busy && <span className="text-sm text-slate-500">{busy}</span>}
          </div>
        )}

        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      </div>

      {/* History */}
      <div className="mt-8">
        <h2 className="text-sm font-semibold text-slate-900">Run history</h2>
        {runs.length === 0 ? (
          <p className="mt-2 text-sm text-slate-400">No runs yet.</p>
        ) : (
          <div className="mt-3 overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs font-medium text-slate-500">
                  <th className="px-4 py-3">Run</th>
                  <th className="px-4 py-3">Reference date</th>
                  <th className="px-4 py-3">Entity</th>
                  <th className="px-4 py-3">Status</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-3">
                      <Link
                        to={`/runs/${r.id}`}
                        className="font-medium text-slate-900 hover:underline"
                      >
                        #{r.id}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-slate-600">{r.reference_date}</td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-500">
                      {r.entity_lei}.{r.entity_scope}
                    </td>
                    <td className="px-4 py-3">
                      <RunStatusBadge status={r.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  )
}
