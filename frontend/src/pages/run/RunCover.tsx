import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { listSnapshots, type Snapshot } from '../../api/snapshots'
import {
  attachFactFile,
  deleteRun,
  DependencyChangedError,
  executeRun,
  listEntities,
  reexecuteRun,
  type DependencyChange,
  type Entity,
  type ReexecuteOptions,
  type Run,
} from '../../api/workflows'
import RunStatusBadge from '../../components/RunStatusBadge'
import UploadZone from '../../components/UploadZone'
import VerdictBanner from '../../components/VerdictBanner'
import { Breadcrumb, Card, ErrorText, primaryBtn, secondaryBtn } from '../../components/ui'
import { formatDate, formatTime } from '../../lib/format'
import { runCrumbs, useRun } from './context'

function KeyChip({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white px-2.5 py-1">
      <div className="text-[10px] font-medium uppercase tracking-wider text-slate-400">
        {label}
      </div>
      <div className="font-mono text-xs tabular-nums text-slate-700">
        {value || <span className="text-slate-300">·</span>}
      </div>
    </div>
  )
}

function StageCard({
  to,
  n,
  title,
  summary,
  accent,
}: {
  to: string
  n: number
  title: string
  summary: React.ReactNode
  accent?: string
}) {
  return (
    <Link
      to={to}
      className="group flex items-center gap-4 rounded-lg border border-slate-200 bg-white px-5 py-4 transition-all hover:border-slate-300 hover:shadow-sm"
    >
      <span
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full font-mono text-xs ${
          accent ?? 'bg-slate-900 text-white'
        }`}
      >
        {n}
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold text-slate-900">{title}</div>
        <div className="mt-0.5 truncate text-xs text-slate-500">{summary}</div>
      </div>
      <span className="shrink-0 text-slate-300 transition-colors group-hover:text-slate-500">
        →
      </span>
    </Link>
  )
}

export default function RunCover() {
  const ctx = useRun()
  const { detail, config, entity, release, entityMissing, releaseMissing,
    facts, siblings, id } = ctx
  const { run, verdict } = detail
  const navigate = useNavigate()

  const [resubmitOpen, setResubmitOpen] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [changes, setChanges] = useState<DependencyChange[] | null>(null)
  const [pickEntities, setPickEntities] = useState<Entity[]>([])
  const [pickReleases, setPickReleases] = useState<Snapshot[]>([])
  const [selEntity, setSelEntity] = useState<number | ''>('')
  const [selRelease, setSelRelease] = useState<number | ''>('')

  const inProgress =
    run.status === 'running' || run.status === 'formula_validation_running'
  const needEntity = (changes ?? []).some((c) => c.kind === 'entity_deleted')
  const needRelease = (changes ?? []).some(
    (c) => c.kind === 'release_deleted' || c.kind === 'release_unavailable',
  )

  // When a vanished dependency must be reselected, load the current options.
  useEffect(() => {
    if (needEntity && pickEntities.length === 0) {
      listEntities().then(setPickEntities).catch(() => {})
    }
    if (needRelease && pickReleases.length === 0) {
      listSnapshots().then(setPickReleases).catch(() => {})
    }
  }, [needEntity, needRelease, pickEntities.length, pickReleases.length])

  // Frozen at execution — read from the run, never the live entity (which is
  // still fetched for other purposes but must not drive historical identity).
  const entityName = run.entity_name ?? entity?.name ?? run.entity_lei
  const templateCount = useMemo(
    () => new Set((facts ?? []).map((f) => f.template_code)).size,
    [facts],
  )
  const fis = detail.filing_indicators ?? []
  const filed = fis.filter((f) => f.reported).length
  const notFiled = fis.length - filed
  const pkg = detail.files.find((f) => f.role === 'package_output')

  async function handleDelete() {
    const message =
      `Delete this execution (#${run.id})?\n\n` +
      'This removes the run and its artifacts — the generated package, the ' +
      'validation report, the input file, and the recorded facts. Other ' +
      'executions of this instance are unaffected. This cannot be undone.'
    if (!window.confirm(message)) return
    setBusy('Deleting…')
    setError(null)
    try {
      await deleteRun(run.id)
      navigate(`/reporting/suites/${run.workflow_id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setBusy(null)
    }
  }

  async function runResubmit(opts: ReexecuteOptions) {
    if (!file) return
    setError(null)
    try {
      setBusy('Creating execution…')
      const fresh = await reexecuteRun(id, opts)
      setChanges(null)
      setBusy('Uploading facts…')
      await attachFactFile(fresh.id, file)
      setBusy('Generating & validating…')
      await executeRun(fresh.id)
      navigate(`/reporting/runs/${fresh.id}`)
    } catch (e) {
      if (e instanceof DependencyChangedError) {
        // The entity or release changed/vanished since the last execution —
        // surface what changed and require a deliberate choice before re-binding.
        setChanges(e.changes)
        setBusy(null)
        return
      }
      setError(e instanceof Error ? e.message : String(e))
      setBusy(null)
    }
  }

  // Resolve the surfaced changes: reselect any vanished dependency, and
  // acknowledge any still-usable change.
  function resolveAndResubmit() {
    void runResubmit({
      acknowledge: true,
      entityId: needEntity && selEntity !== '' ? selEntity : undefined,
      releaseSnapshotId:
        needRelease && selRelease !== '' ? selRelease : undefined,
    })
  }

  const reselectReady =
    (!needEntity || selEntity !== '') && (!needRelease || selRelease !== '')

  const validationSummary =
    verdict.submittable === null
      ? verdict.label
      : `${verdict.blocking} blocking · ${verdict.non_blocking_failures} non-blocking${
          verdict.warnings ? ` · ${verdict.warnings} warning` : ''
        }`

  return (
    <section className="space-y-6">
      <Breadcrumb items={runCrumbs(ctx)} />

      {/* Identity */}
      <Card className="p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold tracking-tight text-slate-900">
              {config?.name ?? 'Submission'}
            </h1>
            <div className="mt-1 text-sm text-slate-600">
              {entityName}
              <span className="mx-2 text-slate-300">·</span>
              <span className="tabular-nums text-slate-500">
                {formatDate(run.reference_date)}
              </span>
              <span className="mx-2 text-slate-300">·</span>
              <span className="font-mono text-xs text-slate-500">
                {run.entity_lei}.{run.entity_scope}
              </span>
            </div>
          </div>
          <div className="text-right">
            <div className="text-[10px] font-medium uppercase tracking-wider text-slate-400">
              Taxonomy
            </div>
            <div className="font-mono text-sm text-slate-800">
              {release?.version_label ?? '—'}
            </div>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <KeyChip label="Snapshot" value={run.snapshot_key} />
          <KeyChip label="Adjusted" value={run.adjusted_key} />
          <KeyChip label="Version" value={run.version_key} />
        </div>
      </Card>

      {(entityMissing || releaseMissing) && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          {entityMissing && releaseMissing
            ? 'The entity and the taxonomy release this run used no longer exist.'
            : entityMissing
              ? 'The entity this run used no longer exists.'
              : 'The taxonomy release this run used no longer exists.'}{' '}
          Its recorded values are shown from the run itself. Re-executing will ask
          you to choose a current one.
        </div>
      )}

      <VerdictBanner verdict={verdict} />

      {/* Executions of this instance */}
      {siblings.length > 1 && (
        <Card className="p-5">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
              Executions · {siblings.length}
            </h2>
          </div>
          <div className="space-y-1">
            {siblings.map((r, i) => (
              <ExecutionRow key={r.id} run={r} current={r.id === id} latest={i === 0} />
            ))}
          </div>
        </Card>
      )}

      {/* Stages */}
      <div className="grid gap-3 sm:grid-cols-2">
        <StageCard
          to={`/reporting/runs/${id}/input`}
          n={1}
          title="Input Data"
          summary={
            facts === null
              ? '…'
              : `${detail.fact_count} facts across ${templateCount} templates`
          }
        />
        <StageCard
          to={`/reporting/runs/${id}/indicators`}
          n={2}
          title="Filing Indicators"
          summary={
            fis.length === 0 ? 'Not derived' : `${filed} filed · ${notFiled} not filed`
          }
        />
        <StageCard
          to={`/reporting/runs/${id}/validation`}
          n={3}
          title="Validation"
          summary={validationSummary}
          accent={
            verdict.submittable === false
              ? 'bg-red-600 text-white'
              : verdict.non_blocking_failures || verdict.warnings
                ? 'bg-amber-500 text-white'
                : undefined
          }
        />
        <StageCard
          to={`/reporting/runs/${id}/package`}
          n={4}
          title="Package"
          summary={pkg ? pkg.filename : 'Not generated'}
        />
      </div>

      {/* Re-execute / resubmit */}
      <Card className="p-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">
              Re-execute / Resubmit
            </h2>
            <p className="mt-0.5 text-xs text-slate-500">
              A full resubmission (FR 1.12): a new execution of this instance with
              a fresh fact file. Earlier executions stay in history.
            </p>
          </div>
          {!resubmitOpen && (
            <button
              type="button"
              className={secondaryBtn}
              onClick={() => setResubmitOpen(true)}
            >
              Re-execute
            </button>
          )}
        </div>
        {resubmitOpen && (
          <div className="mt-4 space-y-3">
            <UploadZone
              accept=".xlsx"
              onFile={setFile}
              file={file}
              hint="Fact file · XLSX"
              disabled={busy !== null}
              compact
            />
            {changes && (
              <div className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3">
                <div className="text-sm font-semibold text-amber-900">
                  {needEntity || needRelease
                    ? 'A dependency is no longer available'
                    : 'Confirm before re-executing'}
                </div>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-amber-900">
                  {changes.map((c, i) => (
                    <li key={i}>{c.message}</li>
                  ))}
                </ul>

                {needEntity && (
                  <label className="mt-3 block text-xs font-medium text-amber-900">
                    Select a current entity
                    <select
                      className="mt-1 block w-full rounded border border-amber-300 bg-white px-2 py-1.5 text-sm text-slate-800"
                      value={selEntity}
                      onChange={(e) => setSelEntity(Number(e.target.value))}
                    >
                      <option value="">Choose an entity…</option>
                      {pickEntities.map((e) => (
                        <option key={e.id} value={e.id}>
                          {e.name} · {e.lei}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                {needRelease && (
                  <label className="mt-3 block text-xs font-medium text-amber-900">
                    Select a current release
                    <select
                      className="mt-1 block w-full rounded border border-amber-300 bg-white px-2 py-1.5 text-sm text-slate-800"
                      value={selRelease}
                      onChange={(e) => setSelRelease(Number(e.target.value))}
                    >
                      <option value="">Choose a release…</option>
                      {pickReleases.map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.display_name}
                        </option>
                      ))}
                    </select>
                  </label>
                )}

                <div className="mt-3 flex items-center gap-3">
                  {needEntity || needRelease ? (
                    <button
                      type="button"
                      className={primaryBtn}
                      disabled={busy !== null || !reselectReady}
                      onClick={resolveAndResubmit}
                    >
                      Continue with selected
                    </button>
                  ) : (
                    <button
                      type="button"
                      className={primaryBtn}
                      disabled={busy !== null}
                      onClick={() => void runResubmit({ acknowledge: true })}
                    >
                      Confirm &amp; re-execute
                    </button>
                  )}
                  <button
                    type="button"
                    className={secondaryBtn}
                    disabled={busy !== null}
                    onClick={() => setChanges(null)}
                  >
                    Cancel
                  </button>
                  {busy && <span className="text-sm text-slate-500">{busy}</span>}
                </div>
              </div>
            )}
            {!changes && (
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  className={primaryBtn}
                  disabled={!file || busy !== null}
                  onClick={() => void runResubmit({})}
                >
                  Resubmit
                </button>
                <button
                  type="button"
                  className={secondaryBtn}
                  disabled={busy !== null}
                  onClick={() => {
                    setResubmitOpen(false)
                    setFile(null)
                    setChanges(null)
                  }}
                >
                  Cancel
                </button>
                {busy && <span className="text-sm text-slate-500">{busy}</span>}
                <ErrorText>{error}</ErrorText>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* Delete this execution */}
      <div className="flex items-center justify-end gap-3">
        {inProgress && (
          <span className="text-xs text-slate-400">
            Still running — wait for it to finish before deleting.
          </span>
        )}
        <button
          type="button"
          disabled={busy !== null || inProgress}
          className="text-xs font-medium text-slate-400 hover:text-red-600 disabled:opacity-50 disabled:hover:text-slate-400"
          onClick={() => void handleDelete()}
        >
          Delete this execution
        </button>
      </div>
    </section>
  )
}

function ExecutionRow({
  run,
  current,
  latest,
}: {
  run: Run
  current: boolean
  latest: boolean
}) {
  const inner = (
    <div
      className={`flex items-center justify-between rounded-md px-3 py-2 ${
        current ? 'bg-slate-100' : 'hover:bg-slate-50'
      }`}
    >
      <div className="flex items-center gap-2.5">
        <span className="font-mono text-xs tabular-nums text-slate-500">
          {formatTime(run.created_at)}
        </span>
        {latest && (
          <span className="rounded bg-slate-900 px-1.5 py-0.5 text-[10px] font-medium text-white">
            Latest
          </span>
        )}
        {current && !latest && (
          <span className="text-[11px] text-slate-400">viewing</span>
        )}
      </div>
      <RunStatusBadge status={run.status} />
    </div>
  )
  return current ? (
    inner
  ) : (
    <Link to={`/reporting/runs/${run.id}`} className="block">
      {inner}
    </Link>
  )
}
