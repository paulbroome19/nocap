import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { listSnapshots, uploadSnapshot, type Snapshot } from '../api/snapshots'
import StatusBadge from '../components/StatusBadge'
import UploadZone from '../components/UploadZone'
import {
  Card,
  EmptyState,
  ErrorText,
  PageHeader,
  TableSkeleton,
  fieldClass,
  primaryBtn,
} from '../components/ui'
import { formatDate } from '../lib/format'

export default function Releases() {
  const navigate = useNavigate()
  const [releases, setReleases] = useState<Snapshot[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [showNew, setShowNew] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [versionLabel, setVersionLabel] = useState('')
  const [progress, setProgress] = useState<number | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      setReleases(await listSnapshots())
      setLoadError(null)
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  // Poll while any release is still ingesting its DPM.
  const anyIngesting = (releases ?? []).some((s) => s.status === 'ingesting')
  useEffect(() => {
    if (!anyIngesting) return
    const id = setInterval(() => void refresh(), 2000)
    return () => clearInterval(id)
  }, [anyIngesting, refresh])

  const canUpload =
    file !== null && versionLabel.trim() !== '' && progress === null

  async function handleCreate() {
    if (!file) return
    setUploadError(null)
    setProgress(0)
    try {
      const created = await uploadSnapshot(file, versionLabel.trim(), setProgress)
      navigate(`/releases/${created.id}`)
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : String(e))
      setProgress(null)
    }
  }

  return (
    <section>
      <PageHeader
        title="Taxonomy Releases"
        actions={
          <button
            type="button"
            className={primaryBtn}
            onClick={() => setShowNew((v) => !v)}
          >
            {showNew ? 'Cancel' : '+ New release'}
          </button>
        }
      />

      {showNew && (
        <Card className="mb-6 p-5">
          <h2 className="text-sm font-semibold text-slate-900">New release</h2>
          <p className="mt-0.5 text-xs text-slate-500">
            Upload the EBA DPM Access database (.accdb) to create the release.
            Ingestion runs in the background; you can add the taxonomy package and
            reference files from the release page.
          </p>
          <div className="mt-4 max-w-lg space-y-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs font-medium text-slate-600">
                Version label
              </span>
              <input
                type="text"
                value={versionLabel}
                onChange={(e) => setVersionLabel(e.target.value)}
                placeholder="e.g. 4.2"
                className={`${fieldClass} w-32`}
              />
            </label>
            <UploadZone
              accept=".accdb,.mdb"
              hint="DPM database · ACCDB / MDB"
              onFile={setFile}
              file={file}
              disabled={progress !== null}
            />
            <button
              type="button"
              onClick={() => void handleCreate()}
              disabled={!canUpload}
              className={primaryBtn}
            >
              {progress === null ? 'Create release' : 'Uploading…'}
            </button>
          </div>

          {progress !== null && (
            <div className="mt-4 max-w-md">
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                <div
                  className="h-full bg-slate-900 transition-[width] duration-150"
                  style={{ width: `${Math.round(progress * 100)}%` }}
                />
              </div>
              <p className="mt-1 text-xs text-slate-500">
                {Math.round(progress * 100)}% uploaded
                {progress >= 1 && ' — registering…'}
              </p>
            </div>
          )}
          <div className="mt-3">
            <ErrorText>{uploadError}</ErrorText>
          </div>
        </Card>
      )}

      <ErrorText>{loadError && `Could not load releases: ${loadError}`}</ErrorText>

      {releases === null && !loadError ? (
        <TableSkeleton />
      ) : releases && releases.length === 0 ? (
        <EmptyState>
          No releases yet. Use <span className="font-medium">+ New release</span>{' '}
          to onboard one.
        </EmptyState>
      ) : (
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs font-medium text-slate-500">
                <th className="px-4 py-3">Version</th>
                <th className="px-4 py-3">DPM file</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Uploaded</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {(releases ?? []).map((s) => (
                <tr
                  key={s.id}
                  onClick={() => navigate(`/releases/${s.id}`)}
                  className="cursor-pointer border-b border-slate-100 transition-colors last:border-0 hover:bg-slate-50"
                >
                  <td className="px-4 py-3 font-medium text-slate-900">
                    {s.version_label}
                  </td>
                  <td className="px-4 py-3 text-slate-600">
                    {s.original_filename}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={s.status} />
                  </td>
                  <td className="px-4 py-3 text-slate-600">
                    {formatDate(s.uploaded_at)}
                  </td>
                  <td className="px-4 py-3 text-right text-slate-300">→</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </section>
  )
}
