import { useEffect, useState, type ReactNode } from 'react'
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
} from '../../api/workflows'
import UploadZone from '../../components/UploadZone'
import VerdictBanner from '../../components/VerdictBanner'
import {
  Block,
  Breadcrumb,
  dangerText,
  ErrorText,
  FieldLabel,
  primaryBtn,
  secondaryBtn,
  SectionLabel,
  Select,
} from '../../components/ui'
import { formatDate } from '../../lib/format'
import { runStatusLabel } from '../../lib/status'
import { runCrumbs, useRun } from './context'

/** A frozen identity field (blank value renders blank — never a dash). */
function IdField({ label, value, mono }: { label: string; value: ReactNode; mono?: boolean }) {
  return (
    <div>
      <div className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted">
        {label}
      </div>
      <div className={`mt-1 text-[14px] text-data ${mono ? 'font-mono' : ''}`}>
        {value}
      </div>
    </div>
  )
}

/** One numbered stage row inside the stages block. */
function Stage({
  n,
  title,
  summary,
  to,
}: {
  n: number
  title: string
  summary: ReactNode
  to?: string
}) {
  const content = (
    <>
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-ink font-mono text-[12px] text-white">
        {n}
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-[15px] font-semibold text-ink">{title}</div>
        <div className="mt-0.5 truncate text-[13px] text-sub">{summary}</div>
      </div>
      {to && <span className="text-[18px] leading-none text-faint">→</span>}
    </>
  )
  const cls =
    'flex items-center gap-4 border-t border-divider px-6 py-[22px] first:border-t-0'
  return to ? (
    <Link to={to} className={`${cls} transition-colors hover:bg-hover`}>
      {content}
    </Link>
  ) : (
    <div className={cls}>{content}</div>
  )
}

export default function RunCover() {
  const ctx = useRun()
  const { detail, config, entity, entityMissing, releaseMissing, release, siblings, id } = ctx
  const { run, verdict } = detail
  const navigate = useNavigate()

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

  useEffect(() => {
    if (needEntity && pickEntities.length === 0)
      listEntities().then(setPickEntities).catch(() => {})
    if (needRelease && pickReleases.length === 0)
      listSnapshots().then(setPickReleases).catch(() => {})
  }, [needEntity, needRelease, pickEntities.length, pickReleases.length])

  // Frozen at execution — read from the run, never the live entity.
  const entityName = run.entity_name ?? entity?.name ?? run.entity_lei
  const inputFile = detail.files.find((f) => f.role === 'fact_input')
  const pkg = detail.files.find((f) => f.role === 'package_output')

  async function handleDelete() {
    const message =
      'Delete this execution?\n\n' +
      'This removes the execution and its artifacts — the generated package, ' +
      'the validation report, the input file, and the recorded facts. Other ' +
      'executions of this submission are unaffected. This cannot be undone.'
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
      setBusy('Generating and validating…')
      await executeRun(fresh.id)
      navigate(`/reporting/runs/${fresh.id}`)
    } catch (e) {
      if (e instanceof DependencyChangedError) {
        setChanges(e.changes)
        setBusy(null)
        return
      }
      setError(e instanceof Error ? e.message : String(e))
      setBusy(null)
    }
  }

  function resolveAndResubmit() {
    void runResubmit({
      acknowledge: true,
      entityId: needEntity && selEntity !== '' ? selEntity : undefined,
      releaseSnapshotId: needRelease && selRelease !== '' ? selRelease : undefined,
    })
  }

  const reselectReady =
    (!needEntity || selEntity !== '') && (!needRelease || selRelease !== '')

  const validationSummary: ReactNode =
    verdict.submittable === null ? (
      verdict.label
    ) : (
      <>
        {verdict.blocking > 0 && (
          <span className="font-semibold text-red">{verdict.blocking} blocking</span>
        )}
        {verdict.blocking > 0 && ' · '}
        {verdict.non_blocking_failures} non-blocking
        {verdict.warnings ? ` · ${verdict.warnings} warning` : ''}
      </>
    )

  return (
    <section>
      <Breadcrumb items={runCrumbs(ctx)} />
      <div className="mb-8">
        <h1 className="text-[32px] font-bold leading-none tracking-[-0.02em] text-ink">
          {config?.name ?? 'Submission'}
        </h1>
        <div className="mt-3 h-[3px] w-12 bg-gold" />
      </div>

      {/* Identity */}
      <SectionLabel>Submission</SectionLabel>
      <Block className="p-6">
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          <IdField label="Entity" value={entityName} />
          <IdField label="Reporting date" value={formatDate(run.reference_date)} mono />
          <IdField
            label="Taxonomy release"
            value={releaseMissing ? '—' : (release?.version_label ?? '')}
          />
          <IdField label="Snapshot" value={run.snapshot_key ?? ''} mono />
          <IdField label="Adjusted" value={run.adjusted_key ?? ''} mono />
          <IdField label="Version" value={run.version_key ?? ''} mono />
        </div>
        {(entityMissing || releaseMissing) && (
          <div className="mt-5 rounded-lg border border-card bg-canvas px-4 py-3 text-[13px] text-sub">
            {entityMissing && releaseMissing
              ? 'The entity and taxonomy release this submission used no longer exist.'
              : entityMissing
                ? 'The entity this submission used no longer exists.'
                : 'The taxonomy release this submission used no longer exists.'}{' '}
            Its recorded values are shown from the submission itself; re-executing
            will ask you to choose a current one.
          </div>
        )}
      </Block>

      {/* Execute — resubmit this instance with a fresh fact file */}
      <div className="mt-8">
        <SectionLabel>Execute</SectionLabel>
        <Block className="p-6">
          <div className="grid gap-5 sm:grid-cols-2">
            <div>
              <FieldLabel>Fact file</FieldLabel>
              <UploadZone accept=".xlsx" onFile={setFile} file={file} hint="XLSX" compact />
            </div>
            <div className="flex items-end">
              <p className="text-[13px] text-sub">
                Upload a fact file and execute to produce a new execution of this
                submission. Earlier executions stay in the record.
              </p>
            </div>
          </div>

          {changes && (
            <div className="mt-5 rounded-lg border border-card bg-canvas px-4 py-4">
              <div className="text-[13px] font-semibold text-ink">
                {needEntity || needRelease
                  ? 'A dependency is no longer available'
                  : 'Confirm before executing'}
              </div>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-[13px] text-sub">
                {changes.map((c, i) => (
                  <li key={i}>{c.message}</li>
                ))}
              </ul>
              {needEntity && (
                <label className="mt-3 block">
                  <FieldLabel>Select a current entity</FieldLabel>
                  <Select value={selEntity} onChange={(v) => setSelEntity(v === '' ? '' : Number(v))}>
                    <option value="">Choose an entity…</option>
                    {pickEntities.map((e) => (
                      <option key={e.id} value={e.id}>{e.name} · {e.lei}</option>
                    ))}
                  </Select>
                </label>
              )}
              {needRelease && (
                <label className="mt-3 block">
                  <FieldLabel>Select a current release</FieldLabel>
                  <Select value={selRelease} onChange={(v) => setSelRelease(v === '' ? '' : Number(v))}>
                    <option value="">Choose a release…</option>
                    {pickReleases.map((r) => (
                      <option key={r.id} value={r.id}>{r.display_name}</option>
                    ))}
                  </Select>
                </label>
              )}
              <div className="mt-4 flex items-center gap-3">
                {needEntity || needRelease ? (
                  <button type="button" className={primaryBtn} disabled={busy !== null || !reselectReady} onClick={resolveAndResubmit}>
                    Continue
                  </button>
                ) : (
                  <button type="button" className={primaryBtn} disabled={busy !== null} onClick={() => void runResubmit({ acknowledge: true })}>
                    Confirm and execute
                  </button>
                )}
                <button type="button" className={secondaryBtn} disabled={busy !== null} onClick={() => setChanges(null)}>
                  Cancel
                </button>
              </div>
            </div>
          )}

          {!changes && (
            <div className="mt-5 flex items-center gap-4">
              <button type="button" className={primaryBtn} disabled={!file || busy !== null} onClick={() => void runResubmit({})}>
                Execute
              </button>
              {busy && <span className="text-[13px] text-sub">{busy}</span>}
              <ErrorText>{error}</ErrorText>
            </div>
          )}
        </Block>
      </div>

      {/* Stages — in process order */}
      <div className="mt-8">
        <SectionLabel>Stages</SectionLabel>
        <Block>
          <Stage
            n={1}
            title="Input Data"
            summary={inputFile ? inputFile.filename : 'No fact file'}
            to={`/reporting/runs/${id}/input`}
          />
          <Stage
            n={2}
            title="Filing Indicators"
            summary="Derived from the submitted facts"
            to={`/reporting/runs/${id}/indicators`}
          />
          <Stage
            n={3}
            title="Parameters"
            summary={`${run.base_currency} · decimals ${run.decimals}`}
          />
          <Stage
            n={4}
            title="Validation"
            summary={validationSummary}
            to={`/reporting/runs/${id}/validation`}
          />
          <Stage
            n={5}
            title="Package"
            summary={pkg ? pkg.filename : 'Not generated'}
            to={`/reporting/runs/${id}/package`}
          />
        </Block>
      </div>

      {/* Executions — earlier executions of this submission stay visible */}
      {siblings.length > 1 && (
        <div className="mt-8">
          <SectionLabel>Executions</SectionLabel>
          <Block>
            {siblings.map((s, i) => (
              <Link
                key={s.id}
                to={`/reporting/runs/${s.id}`}
                className="flex items-center justify-between gap-4 border-t border-divider px-6 py-4 transition-colors first:border-t-0 hover:bg-hover"
              >
                <span className="flex items-center gap-3 text-[13px]">
                  <span className="font-mono text-data">{formatDate(s.created_at)}</span>
                  {i === 0 && (
                    <span className="rounded bg-ink px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-white">
                      Latest
                    </span>
                  )}
                  {s.id === id && i !== 0 && (
                    <span className="text-[11px] text-muted">viewing</span>
                  )}
                </span>
                <span className="text-[13px] text-sub">{runStatusLabel(s.status)}</span>
              </Link>
            ))}
          </Block>
        </div>
      )}

      {/* Verdict — last */}
      <div className="mt-8">
        <SectionLabel>Verdict</SectionLabel>
        <VerdictBanner verdict={verdict} />
      </div>

      {/* Delete — from the execution's own page; blocked while in progress */}
      <div className="mt-8 flex items-center justify-end gap-3">
        {inProgress && (
          <span className="text-[13px] text-muted">
            Still running — wait for it to finish before deleting.
          </span>
        )}
        <button
          type="button"
          disabled={busy !== null || inProgress}
          className={`${dangerText} disabled:hover:text-sub`}
          onClick={() => void handleDelete()}
        >
          Delete this execution
        </button>
      </div>
    </section>
  )
}
