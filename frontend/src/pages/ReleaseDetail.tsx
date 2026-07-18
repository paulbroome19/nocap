import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  getReleaseDetail,
  reingestSnapshot,
  uploadArtifact,
  type ArtifactStatus,
  type Capabilities,
  type ReleaseDetail as ReleaseDetailT,
  type ReleaseSlot,
} from '../api/snapshots'
import {
  Card,
  ErrorText,
  Loading,
  PageHeader,
  secondaryBtn,
} from '../components/ui'
import UploadZone from '../components/UploadZone'
import { formatDate } from '../lib/format'

const STATUS_STYLES: Record<ArtifactStatus, string> = {
  empty: 'bg-slate-100 text-slate-500 ring-slate-500/20',
  uploaded: 'bg-sky-100 text-sky-800 ring-sky-600/20',
  verifying: 'bg-amber-100 text-amber-800 ring-amber-600/20',
  ready: 'bg-emerald-100 text-emerald-800 ring-emerald-600/20',
  failed: 'bg-red-100 text-red-800 ring-red-600/20',
}

const REQUIREMENT_LABEL: Record<string, string> = {
  required: 'Required',
  formula: 'Required for formula validation',
  register: 'Required for rule register',
  reference: 'Reference',
}

const REQUIREMENT_STYLES: Record<string, string> = {
  required: 'bg-slate-900 text-white',
  formula: 'bg-sky-50 text-sky-700 ring-1 ring-inset ring-sky-600/20',
  register: 'bg-sky-50 text-sky-700 ring-1 ring-inset ring-sky-600/20',
  reference: 'bg-slate-100 text-slate-500',
}

const CAPABILITIES: { key: keyof Capabilities; label: string }[] = [
  { key: 'resolve', label: 'Resolve' },
  { key: 'generate', label: 'Generate' },
  { key: 'formula_validate', label: 'Formula validate' },
  { key: 'rule_register', label: 'Rule register' },
]

function CapabilityPanel({ caps }: { caps: Capabilities }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {CAPABILITIES.map(({ key, label }) => {
        const on = caps[key]
        const suffix =
          key === 'generate' && caps.verified_entry_points
            ? ' · verified entry points'
            : ''
        return (
          <span
            key={key}
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${
              on
                ? 'bg-emerald-50 text-emerald-800 ring-1 ring-inset ring-emerald-600/20'
                : 'bg-slate-50 text-slate-400 ring-1 ring-inset ring-slate-400/15'
            }`}
          >
            <span aria-hidden>{on ? '✓' : '○'}</span>
            {label}
            {on && suffix}
          </span>
        )
      })}
    </div>
  )
}

function SlotStatus({ status }: { status: ArtifactStatus }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${STATUS_STYLES[status]}`}
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
  const [detail, setDetail] = useState<ReleaseDetailT | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Per-slot upload state.
  const [busySlot, setBusySlot] = useState<string | null>(null)
  const [progress, setProgress] = useState<number | null>(null)
  const [slotError, setSlotError] = useState<Record<string, string>>({})
  const [reingesting, setReingesting] = useState(false)

  const load = useCallback(() => {
    getReleaseDetail(id)
      .then(setDetail)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  // Poll while the DPM is ingesting or any slot (e.g. the workbook) is verifying.
  const busy =
    detail?.release.status === 'ingesting' ||
    (detail?.slots.some((s) => s.status === 'verifying') ?? false)
  useEffect(() => {
    if (!busy) return
    const t = setInterval(load, 2000)
    return () => clearInterval(t)
  }, [busy, load])

  async function handleUpload(slot: ReleaseSlot, file: File) {
    setBusySlot(slot.slot)
    setProgress(0)
    setSlotError((e) => ({ ...e, [slot.slot]: '' }))
    try {
      const updated = await uploadArtifact(id, slot.slot, file, setProgress)
      setDetail(updated)
    } catch (e) {
      setSlotError((prev) => ({
        ...prev,
        [slot.slot]: e instanceof Error ? e.message : String(e),
      }))
      load()
    } finally {
      setBusySlot(null)
      setProgress(null)
    }
  }

  async function handleReingest() {
    setReingesting(true)
    try {
      await reingestSnapshot(id)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setReingesting(false)
    }
  }

  if (error) return <ErrorText>{error}</ErrorText>
  if (!detail) return <Loading />

  const { release, ready, slots, capabilities, coherence_warnings } = detail
  const functional = slots.filter((s) => s.requirement !== 'reference')
  const reference = slots.filter((s) => s.requirement === 'reference')

  const renderSlot = (slot: ReleaseSlot) => {
    const isDpm = slot.slot === 'dpm_database'
    const isBusy = busySlot === slot.slot
    const canReingest =
      isDpm && (slot.status === 'failed' || release.status === 'artifacts_missing')
    return (
      <Card key={slot.slot} className="flex flex-col p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">
              {slot.label}
            </h2>
            <span
              className={`mt-1 inline-block rounded px-1.5 py-0.5 text-[11px] font-medium ${REQUIREMENT_STYLES[slot.requirement]}`}
            >
              {REQUIREMENT_LABEL[slot.requirement]}
            </span>
          </div>
          <SlotStatus status={slot.status} />
        </div>

        <p className="mt-3 text-xs leading-relaxed text-slate-500">
          {slot.description}
        </p>

        {slot.filename && (
          <div className="mt-3 rounded-md bg-slate-50 px-3 py-2">
            <div className="truncate font-mono text-xs text-slate-700">
              {slot.filename}
            </div>
            {slot.uploaded_at && (
              <div className="mt-0.5 text-[11px] text-slate-400">
                {formatDate(slot.uploaded_at)}
              </div>
            )}
          </div>
        )}

        {slot.status === 'failed' && slot.error && (
          <p className="mt-2 text-xs text-red-600">{slot.error}</p>
        )}

        {/* Controls */}
        <div className="mt-4 flex-1" />
        <div className="mt-2">
          {isDpm ? (
            canReingest ? (
              <button
                type="button"
                onClick={() => void handleReingest()}
                disabled={reingesting}
                className={secondaryBtn}
              >
                {reingesting ? 'Re-ingesting…' : 'Re-ingest'}
              </button>
            ) : (
              <p className="text-xs text-slate-400">
                Set when the release was created; re-ingest rebuilds it.
              </p>
            )
          ) : (
            <div className="flex flex-col gap-1">
              <UploadZone
                accept={slot.accept.join(',')}
                hint={slot.accept.join(' · ').replace(/\./g, '').toUpperCase()}
                onFile={(f) => {
                  if (f) void handleUpload(slot, f)
                }}
                file={null}
                disabled={isBusy}
                compact
              />
              {isBusy && progress !== null && (
                <span className="text-xs text-slate-500">
                  Uploading… {Math.round(progress * 100)}%
                </span>
              )}
              {slotError[slot.slot] && (
                <span className="text-xs text-red-600">
                  {slotError[slot.slot]}
                </span>
              )}
            </div>
          )}
        </div>
      </Card>
    )
  }

  return (
    <section>
      <PageHeader
        back={{ to: '/releases', label: 'Taxonomy Releases' }}
        title={
          <span className="flex items-center gap-3">
            Release {release.version_label}
            <span
              className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                ready
                  ? 'bg-emerald-100 text-emerald-800'
                  : 'bg-amber-100 text-amber-800'
              }`}
            >
              {ready ? 'Ready' : 'Not ready'}
            </span>
          </span>
        }
      />

      <Card className="mb-4 p-5">
        <CapabilityPanel caps={capabilities} />
        {coherence_warnings.length > 0 && (
          <ul className="mt-4 space-y-1.5 border-t border-slate-100 pt-3">
            {coherence_warnings.map((w) => (
              <li
                key={w}
                className="flex items-start gap-2 text-xs text-amber-700"
              >
                <span aria-hidden>⚠</span>
                {w}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <div className="grid gap-4 sm:grid-cols-3">
        {functional.map(renderSlot)}
      </div>

      {reference.length > 0 && (
        <>
          <h2 className="mt-8 mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">
            Reference
          </h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {reference.map(renderSlot)}
          </div>
        </>
      )}
    </section>
  )
}
