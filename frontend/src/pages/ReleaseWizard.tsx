import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  createRelease,
  getRegulator,
  getSnapshotOrNull,
  type Regulator,
} from '../api/snapshots'
import UploadZone from '../components/UploadZone'
import {
  Block,
  ErrorText,
  FieldLabel,
  PageHeader,
  SectionLabel,
  fieldClass,
  primaryBtn,
} from '../components/ui'

// The three mandatory artifacts, in the regulator's own page order and
// vocabulary, each warning about the file it is easily confused with.
const SLOTS = [
  {
    key: 'rules' as const,
    label: 'Validation rules',
    accept: '.xlsx',
    hint: 'xlsx',
    warn: 'The “Validation rules” workbook the regulator publishes — not a filing-rules PDF.',
  },
  {
    key: 'dpm' as const,
    label: 'DPM database',
    accept: '.accdb,.mdb,.sqlite,.sqlite3,.db',
    hint: 'accdb',
    warn: 'The DPM 2.0 database — not the older DPM 1.0. A pre-converted .sqlite is accepted in its place.',
  },
  {
    key: 'taxonomy' as const,
    label: 'Taxonomy package',
    accept: '.zip',
    hint: 'zip',
    warn: 'The “Taxonomy package” zip — not the much larger “Full taxonomy”.',
  },
]

type Files = { dpm: File | null; taxonomy: File | null; rules: File | null }

export default function ReleaseWizard() {
  const { regulatorId } = useParams()
  const id = Number(regulatorId)
  const navigate = useNavigate()

  const [regulator, setRegulator] = useState<Regulator | null>(null)
  const [versionLabel, setVersionLabel] = useState('')
  const [files, setFiles] = useState<Files>({ dpm: null, taxonomy: null, rules: null })
  const [phase, setPhase] = useState<'idle' | 'uploading' | 'creating'>('idle')
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)
  // True only once the component has really unmounted, so an in-flight poll
  // stops touching state. Reset on (re)mount: React Strict Mode runs effects
  // setup→cleanup→setup in dev, so without the reset the cleanup would leave
  // this stuck `true` and the poll loop would never run.
  const cancelled = useRef(false)

  useEffect(() => {
    getRegulator(id).then(setRegulator).catch(() => {})
  }, [id])

  useEffect(() => {
    cancelled.current = false
    return () => {
      cancelled.current = true
    }
  }, [])

  const ready =
    versionLabel.trim() !== '' &&
    files.dpm !== null &&
    files.taxonomy !== null &&
    files.rules !== null &&
    phase === 'idle'

  async function handleCreate() {
    if (!files.dpm || !files.taxonomy || !files.rules) return
    setError(null)
    setPhase('uploading')
    setProgress(0)
    try {
      // The upload returns once the files are verified and stored; the release
      // comes back `ingesting` while the DPM converts server-side.
      const release = await createRelease(
        id,
        versionLabel.trim(),
        { dpm: files.dpm, taxonomy: files.taxonomy, rules: files.rules },
        (f) => {
          setProgress(f)
          if (f >= 1) setPhase('creating')
        },
      )
      setPhase('creating')
      await pollUntilReady(release.id)
    } catch (e) {
      // Verification rejected a file (or the network dropped) — nothing was
      // created; keep the files so the wrong one can be swapped.
      if (!cancelled.current) {
        setError(e instanceof Error ? e.message : String(e))
        setPhase('idle')
      }
    }
  }

  /**
   * Poll the release until the background conversion finishes. `ready` →
   * navigate to it (shown only once complete). Gone (404) → the background
   * stage failed and cleaned itself up, leaving nothing behind; report it and
   * let the user retry. Transient errors are ignored and retried.
   */
  async function pollUntilReady(releaseId: number) {
    const deadline = Date.now() + 15 * 60 * 1000 // conversion can take minutes
    while (!cancelled.current && Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, 3000))
      if (cancelled.current) return
      let snap
      try {
        snap = await getSnapshotOrNull(releaseId)
      } catch {
        continue // a blip; keep polling
      }
      if (cancelled.current) return
      if (snap === null) {
        setError(
          'The release could not be completed — the DPM database could not be ' +
            'converted. Nothing was saved; check the DPM file and try again.',
        )
        setPhase('idle')
        return
      }
      if (snap.status === 'ready') {
        navigate(`/releases/${releaseId}`)
        return
      }
      if (snap.status === 'failed') {
        setError(snap.error ?? 'The release could not be completed.')
        setPhase('idle')
        return
      }
      // still `ingesting` — keep waiting
    }
    if (!cancelled.current) {
      setError(
        'The release is taking longer than expected to convert. It will appear ' +
          'in the releases list once it finishes.',
      )
      setPhase('idle')
    }
  }

  return (
    <section>
      <PageHeader
        crumbs={[
          { label: 'Taxonomies', to: '/releases' },
          { label: regulator?.name ?? '', to: `/releases/regulators/${id}` },
          { label: 'New release' },
        ]}
        title="New release"
        subtitle="All three published files are required. Each is checked as it arrives; the release is created only once every one is valid — a failure leaves nothing behind."
      />

      <SectionLabel>Release files</SectionLabel>
      <Block className="space-y-6 p-6">
        <label className="block max-w-xs">
          <FieldLabel>Version label</FieldLabel>
          <input
            type="text"
            value={versionLabel}
            onChange={(e) => setVersionLabel(e.target.value)}
            placeholder="e.g. 4.2"
            disabled={phase !== 'idle'}
            className={fieldClass}
          />
        </label>

        <div className="space-y-5">
          {SLOTS.map((s) => (
            <div key={s.key} className="grid gap-4 sm:grid-cols-[1fr_1.4fr] sm:items-center">
              <div>
                <div className="text-[15px] font-semibold text-ink">{s.label}</div>
                <p className="mt-1 text-[12.5px] text-sub">{s.warn}</p>
              </div>
              <UploadZone
                accept={s.accept}
                hint={s.hint}
                file={files[s.key]}
                disabled={phase !== 'idle'}
                onFile={(f) => setFiles((prev) => ({ ...prev, [s.key]: f }))}
              />
            </div>
          ))}
        </div>

        {error && <ErrorText>{error}</ErrorText>}

        <div className="flex items-center gap-4 pt-1">
          <button type="button" onClick={() => void handleCreate()} disabled={!ready} className={primaryBtn}>
            Create
          </button>
          {phase === 'uploading' && (
            <span className="text-[13px] text-sub">
              Uploading the files… {Math.round(progress * 100)}%
            </span>
          )}
          {phase === 'creating' && (
            <span className="inline-flex items-center gap-2 text-[13px] text-sub">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted" />
              Converting the DPM database and ingesting the rules — this can take
              several minutes. Keep this tab open; you’ll be taken to the release
              when it’s ready.
            </span>
          )}
        </div>
      </Block>
    </section>
  )
}
