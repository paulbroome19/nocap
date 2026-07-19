import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  deleteRelease,
  getReleaseDetail,
  reingestSnapshot,
  type ArtifactStatus,
  type ReleaseDetail as ReleaseDetailT,
} from '../api/snapshots'
import {
  Block,
  ErrorText,
  Loading,
  PageHeader,
  SectionLabel,
  dangerText,
  secondaryBtn,
} from '../components/ui'
import { formatDate } from '../lib/format'

const SLOT_LABEL: Record<ArtifactStatus, string> = {
  empty: 'Not provided',
  uploaded: 'Uploaded',
  verifying: 'Verifying',
  ready: 'Ready',
  failed: 'Failed',
}
const SLOT_STYLE: Record<ArtifactStatus, string> = {
  empty: 'text-muted',
  uploaded: 'text-data',
  verifying: 'text-muted',
  ready: 'text-data',
  failed: 'text-red',
}

function SlotStatus({ status }: { status: ArtifactStatus }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[13px] font-medium">
      {status === 'verifying' && (
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted" />
      )}
      <span className={SLOT_STYLE[status]}>{SLOT_LABEL[status]}</span>
    </span>
  )
}

export default function ReleaseDetail() {
  const { snapshotId } = useParams()
  const id = Number(snapshotId)
  const navigate = useNavigate()
  const [detail, setDetail] = useState<ReleaseDetailT | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    getReleaseDetail(id)
      .then(setDetail)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  const converting =
    detail?.release.status === 'ingesting' ||
    (detail?.slots.some((s) => s.status === 'verifying') ?? false)
  useEffect(() => {
    if (!converting) return
    const t = setInterval(load, 2500)
    return () => clearInterval(t)
  }, [converting, load])

  async function handleReingest() {
    setActionError(null)
    setBusy(true)
    try {
      await reingestSnapshot(id)
      load()
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function handleDelete() {
    if (!detail) return
    const message =
      `Delete ${detail.release.display_name}?\n\n` +
      'This removes the DPM database, the taxonomy package, the validation-rules ' +
      'workbook, the ingested validation rules, and every stored file for this ' +
      'release. Submissions already produced from it are unaffected. This cannot ' +
      'be undone.'
    if (!window.confirm(message)) return
    setActionError(null)
    setBusy(true)
    try {
      await deleteRelease(id)
      navigate(`/releases/regulators/${detail.release.regulator_id}`)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
      setBusy(false)
    }
  }

  if (error) return <ErrorText>{error}</ErrorText>
  if (!detail) return <Loading />

  const { release, ready, slots, coherence_warnings } = detail
  const failed = release.status === 'failed' || release.status === 'artifacts_missing'
  const statusLabel = ready ? 'Ready' : failed ? 'Not usable' : 'Preparing'

  return (
    <section>
      <PageHeader
        crumbs={[
          { label: 'Taxonomies', to: '/releases' },
          { label: release.regulator_name, to: `/releases/regulators/${release.regulator_id}` },
          { label: release.version_label },
        ]}
        title={release.display_name}
        actions={
          <span className="flex items-center gap-4">
            <span className={`text-[13px] font-medium ${failed ? 'text-red' : 'text-data'}`}>
              {statusLabel}
            </span>
            <button type="button" onClick={() => void handleDelete()} disabled={busy} className={secondaryBtn}>
              Delete
            </button>
          </span>
        }
      />

      {actionError && <div className="mb-6"><ErrorText>{actionError}</ErrorText></div>}

      {failed && (
        <div className="mb-6 rounded-[14px] border border-card bg-canvas px-5 py-4">
          <p className="text-[14px] text-red">
            {release.error ?? 'This release is not usable.'}
          </p>
          <button type="button" onClick={() => void handleReingest()} disabled={busy} className={`${dangerText} mt-3`}>
            {busy ? 'Rebuilding…' : 'Rebuild from the stored files'}
          </button>
        </div>
      )}

      {coherence_warnings.length > 0 && (
        <div className="mb-6 rounded-[14px] border border-card border-l-2 border-l-red bg-canvas px-5 py-4">
          <div className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 rounded-full bg-red" />
            <span className="text-[11px] font-bold uppercase tracking-[0.14em] text-red">
              Version mismatch
            </span>
          </div>
          <ul className="mt-2.5 space-y-1.5 text-[13px] text-data">
            {coherence_warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      )}

      <SectionLabel>Artifacts</SectionLabel>
      <div className="grid gap-4 sm:grid-cols-3">
        {slots.map((slot) => (
          <Block key={slot.slot} className="p-5">
            <div className="flex items-start justify-between gap-3">
              <h2 className="text-[15px] font-semibold text-ink">{slot.label}</h2>
              <SlotStatus status={slot.status} />
            </div>
            <p className="mt-3 text-[13px] leading-relaxed text-sub">{slot.description}</p>
            {slot.status === 'failed' && slot.error && (
              <p className="mt-2 text-[13px] text-red">{slot.error}</p>
            )}
          </Block>
        ))}
      </div>

      {/* Technical identifiers are evidence, not interface — behind a disclosure. */}
      <details className="mt-6 overflow-hidden rounded-[14px] border border-card bg-page">
        <summary className="cursor-pointer px-6 py-4 text-[12px] font-medium uppercase tracking-[0.1em] text-muted hover:text-sub">
          Audit details
        </summary>
        <div className="border-t border-divider px-6 py-4">
          <dl className="space-y-2.5 text-[13px]">
            <div className="flex gap-4">
              <dt className="w-32 shrink-0 text-muted">Uploaded</dt>
              <dd className="font-mono text-data">{formatDate(release.uploaded_at)}</dd>
            </div>
            <div className="flex gap-4">
              <dt className="w-32 shrink-0 text-muted">DPM file</dt>
              <dd className="font-mono text-data">{release.original_filename}</dd>
            </div>
            <div className="flex gap-4">
              <dt className="w-32 shrink-0 text-muted">DPM source</dt>
              <dd className="text-data">{release.dpm_source_label}</dd>
            </div>
            <div className="flex gap-4">
              <dt className="w-32 shrink-0 text-muted">DPM checksum</dt>
              <dd className="break-all font-mono text-muted">{release.checksum}</dd>
            </div>
            {slots.map((slot) =>
              slot.filename ? (
                <div key={slot.slot} className="flex gap-4">
                  <dt className="w-32 shrink-0 text-muted">{slot.label}</dt>
                  <dd className="font-mono text-data">{slot.filename}</dd>
                </div>
              ) : null,
            )}
          </dl>
        </div>
      </details>
    </section>
  )
}
