import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  createRelease,
  getRegulator,
  type Regulator,
} from '../api/snapshots'
import UploadZone from '../components/UploadZone'
import { Card, PageHeader, fieldClass, primaryBtn } from '../components/ui'

// The three mandatory artifacts, named in EBA-website terms.
const SLOTS = [
  {
    key: 'dpm' as const,
    label: 'DPM database',
    accept: '.accdb,.mdb,.sqlite,.sqlite3,.db',
    hint: 'EBA “DPM 2.0” Access database · .accdb (or a pre-converted .sqlite)',
  },
  {
    key: 'taxonomy' as const,
    label: 'Taxonomy package',
    accept: '.zip',
    hint: 'EBA “Reporting frameworks” taxonomy package · .zip',
  },
  {
    key: 'rules' as const,
    label: 'Validation rules',
    accept: '.xlsx',
    hint: 'EBA “Validation rules” workbook · .xlsx',
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
      // Verified + accepted — the release now converts in the background.
      navigate(`/releases/${release.id}`)
    } catch (e) {
      // A verification failure: nothing was created; keep the files so the
      // reporter can swap the one that was wrong.
      setError(e instanceof Error ? e.message : String(e))
      setPhase('idle')
    }
  }

  return (
    <section>
      <PageHeader
        crumbs={[
          { label: 'Taxonomies', to: '/releases' },
          {
            label: regulator?.name ?? '',
            to: `/releases/regulators/${id}`,
          },
          { label: 'New release' },
        ]}
        title="New taxonomy release"
        subtitle="All three files are required. Each is checked on arrival; the release is created only if all three are valid."
      />

      <Card className="space-y-5 p-6">
        <label className="flex max-w-xs flex-col gap-1">
          <span className="text-xs font-medium text-slate-600">
            Version label
          </span>
          <input
            type="text"
            value={versionLabel}
            onChange={(e) => setVersionLabel(e.target.value)}
            placeholder="e.g. 4.2"
            disabled={phase !== 'idle'}
            className={fieldClass}
          />
        </label>

        <div className="grid gap-4 sm:grid-cols-3">
          {SLOTS.map((s) => (
            <div key={s.key} className="flex flex-col gap-1.5">
              <span className="text-xs font-semibold text-slate-700">
                {s.label}
              </span>
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

        <details className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-600">
          <summary className="cursor-pointer font-medium text-slate-700">
            Is the DPM database too large to upload? Convert it first
          </summary>
          <div className="mt-3 space-y-2">
            <p>
              The EBA “DPM 2.0” database is a Microsoft Access file of around
              720&nbsp;MB — large and slow to upload. You can convert it to a
              compact database (about 80&nbsp;MB) on your own computer and upload
              that instead. It produces exactly the same result.
            </p>
            <p>
              Once (install the converter):{' '}
              <code className="rounded bg-slate-200 px-1 py-0.5">
                brew install mdbtools
              </code>{' '}
              on macOS, or{' '}
              <code className="rounded bg-slate-200 px-1 py-0.5">
                sudo apt-get install -y mdbtools
              </code>{' '}
              on Ubuntu.
            </p>
            <p>Then, from the project’s{' '}
              <code className="rounded bg-slate-200 px-1 py-0.5">backend</code>{' '}
              folder, run:
            </p>
            <pre className="overflow-x-auto rounded bg-slate-800 px-3 py-2 text-[11px] text-slate-100">
              python -m app.taxonomy.convert "DPM_Database_2.0.accdb" dpm.sqlite
            </pre>
            <p>
              Upload the resulting <code className="rounded bg-slate-200 px-1 py-0.5">
              dpm.sqlite</code> here in place of the .accdb. Full steps are in{' '}
              <code className="rounded bg-slate-200 px-1 py-0.5">
                docs/deployment.md
              </code>.
            </p>
          </div>
        </details>

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={() => void handleCreate()}
            disabled={!ready}
            className={primaryBtn}
          >
            Create release
          </button>
          {phase === 'uploading' && (
            <span className="text-sm text-slate-500">
              Uploading… {Math.round(progress * 100)}%
            </span>
          )}
          {phase === 'creating' && (
            <span className="text-sm text-slate-500">Verifying files…</span>
          )}
        </div>
        {phase === 'idle' && !error && (
          <p className="text-xs text-slate-400">
            After the files verify, the DPM database converts in the background —
            this takes a few minutes.
          </p>
        )}
      </Card>
    </section>
  )
}
