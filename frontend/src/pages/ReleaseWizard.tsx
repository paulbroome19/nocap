import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { createRelease, getRegulator, type Regulator } from '../api/snapshots'
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

  useEffect(() => {
    getRegulator(id).then(setRegulator).catch(() => {})
  }, [id])

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
      const release = await createRelease(
        id,
        versionLabel.trim(),
        { dpm: files.dpm, taxonomy: files.taxonomy, rules: files.rules },
        (f) => {
          setProgress(f)
          if (f >= 1) setPhase('creating')
        },
      )
      navigate(`/releases/${release.id}`)
    } catch (e) {
      // Nothing was created; keep the files so the wrong one can be swapped.
      setError(e instanceof Error ? e.message : String(e))
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
            <span className="text-[13px] text-sub">Uploading… {Math.round(progress * 100)}%</span>
          )}
          {phase === 'creating' && (
            <span className="text-[13px] text-sub">
              Verifying the files, converting the DPM database, and ingesting the
              rules… this can take a minute.
            </span>
          )}
        </div>
      </Block>
    </section>
  )
}
