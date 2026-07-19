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
  Card,
  ErrorText,
  Loading,
  PageHeader,
  secondaryBtn,
} from '../components/ui'
import { formatDate } from '../lib/format'

const STATUS_STYLES: Record<ArtifactStatus, string> = {
  empty: 'bg-slate-100 text-slate-500',
  uploaded: 'bg-sky-100 text-sky-800',
  verifying: 'bg-amber-100 text-amber-800',
  ready: 'bg-emerald-100 text-emerald-800',
  failed: 'bg-red-100 text-red-800',
}

function SlotStatus({ status }: { status: ArtifactStatus }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLES[status]}`}
    >
      {status === 'verifying' && (
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-500" />
      )}
      {status}
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

  // Poll while the DPM converts or any slot is still verifying.
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
      'This removes the DPM database, the taxonomy package, the filing-rules ' +
      'workbook, the ingested validation rules, and every stored file for this ' +
      'release. Runs already produced from it are unaffected. This cannot be ' +
      'undone.'
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

  return (
    <section>
      <PageHeader
        crumbs={[
          { label: 'Taxonomies', to: '/releases' },
          {
            label: release.regulator_name,
            to: `/releases/regulators/${release.regulator_id}`,
          },
          { label: release.version_label },
        ]}
        title={
          <span className="flex items-center gap-3">
            {release.display_name}
            <span
              className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                ready
                  ? 'bg-emerald-100 text-emerald-800'
                  : failed
                    ? 'bg-red-100 text-red-800'
                    : 'bg-amber-100 text-amber-800'
              }`}
            >
              {ready ? 'Ready' : failed ? 'Failed' : 'Converting'}
            </span>
          </span>
        }
        actions={
          <button
            type="button"
            onClick={() => void handleDelete()}
            disabled={busy}
            className={secondaryBtn}
          >
            Delete
          </button>
        }
      />

      {actionError && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {actionError}
        </div>
      )}

      {release.status === 'ingesting' && (
        <div className="mb-4 flex items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-amber-500" />
          Converting the DPM database — this takes a few minutes.
        </div>
      )}

      {failed && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3">
          <p className="text-sm text-red-800">{release.error ?? 'This release failed.'}</p>
          <button
            type="button"
            onClick={() => void handleReingest()}
            disabled={busy}
            className={`${secondaryBtn} mt-3`}
          >
            {busy ? 'Re-ingesting…' : 'Re-ingest'}
          </button>
        </div>
      )}

      {coherence_warnings.length > 0 && (
        <Card className="mb-4 p-4">
          <ul className="space-y-1.5">
            {coherence_warnings.map((w) => (
              <li key={w} className="flex items-start gap-2 text-xs text-amber-700">
                <span aria-hidden>⚠</span>
                {w}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        {slots.map((slot) => (
          <Card key={slot.slot} className="p-5">
            <div className="flex items-start justify-between gap-3">
              <h2 className="text-sm font-semibold text-slate-900">{slot.label}</h2>
              <SlotStatus status={slot.status} />
            </div>
            <p className="mt-3 text-xs leading-relaxed text-slate-500">
              {slot.description}
            </p>
            {slot.status === 'failed' && slot.error && (
              <p className="mt-2 text-xs text-red-600">{slot.error}</p>
            )}
          </Card>
        ))}
      </div>

      {/* Technical identifiers are evidence, not interface. */}
      <details className="mt-6 rounded-lg border border-slate-200 bg-white">
        <summary className="cursor-pointer px-4 py-3 text-xs font-medium text-slate-500 hover:text-slate-700">
          Audit details
        </summary>
        <div className="border-t border-slate-100 px-4 py-3">
          <dl className="space-y-2 text-xs">
            <div className="flex gap-3">
              <dt className="w-32 shrink-0 text-slate-400">Uploaded</dt>
              <dd className="tabular-nums text-slate-600">
                {formatDate(release.uploaded_at)}
              </dd>
            </div>
            <div className="flex gap-3">
              <dt className="w-32 shrink-0 text-slate-400">DPM file</dt>
              <dd className="font-mono text-slate-600">{release.original_filename}</dd>
            </div>
            <div className="flex gap-3">
              <dt className="w-32 shrink-0 text-slate-400">DPM source</dt>
              <dd className="text-slate-600">{release.dpm_source_label}</dd>
            </div>
            <div className="flex gap-3">
              <dt className="w-32 shrink-0 text-slate-400">DPM checksum</dt>
              <dd className="break-all font-mono text-slate-400">{release.checksum}</dd>
            </div>
            {slots.map((slot) =>
              slot.filename ? (
                <div key={slot.slot} className="flex gap-3">
                  <dt className="w-32 shrink-0 text-slate-400">{slot.label}</dt>
                  <dd className="font-mono text-slate-600">{slot.filename}</dd>
                </div>
              ) : null,
            )}
          </dl>
        </div>
      </details>
    </section>
  )
}
