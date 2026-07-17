import { useCallback, useEffect, useRef, useState } from 'react'
import {
  listSnapshots,
  uploadSnapshot,
  type Snapshot,
} from '../api/snapshots'
import StatusBadge from '../components/StatusBadge'

function formatDate(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

export default function Snapshots() {
  const [snapshots, setSnapshots] = useState<Snapshot[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)

  const [file, setFile] = useState<File | null>(null)
  const [versionLabel, setVersionLabel] = useState('')
  const [progress, setProgress] = useState<number | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  const refresh = useCallback(async () => {
    try {
      setSnapshots(await listSnapshots())
      setLoadError(null)
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  // Poll while any snapshot is still ingesting.
  const anyIngesting = snapshots.some((s) => s.status === 'ingesting')
  useEffect(() => {
    if (!anyIngesting) return
    const id = setInterval(() => void refresh(), 2000)
    return () => clearInterval(id)
  }, [anyIngesting, refresh])

  const canUpload = file !== null && versionLabel.trim() !== '' && progress === null

  async function handleUpload() {
    if (!file) return
    setUploadError(null)
    setProgress(0)
    try {
      await uploadSnapshot(file, versionLabel.trim(), setProgress)
      setFile(null)
      setVersionLabel('')
      if (fileInput.current) fileInput.current.value = ''
      await refresh()
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : String(e))
    } finally {
      setProgress(null)
    }
  }

  return (
    <section>
      <h1 className="text-2xl font-semibold tracking-tight">Snapshots</h1>
      <p className="mt-1 text-sm text-slate-500">
        Uploaded EBA DPM taxonomy releases — immutable, versioned snapshots.
      </p>

      {/* Upload panel */}
      <div className="mt-6 rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="text-sm font-semibold text-slate-900">Upload a DPM release</h2>
        <p className="mt-0.5 text-xs text-slate-500">
          Accepts the EBA DPM Access database (.accdb). Ingestion runs in the
          background; status updates automatically.
        </p>

        <div className="mt-4 flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-slate-600">
              Version label
            </span>
            <input
              type="text"
              value={versionLabel}
              onChange={(e) => setVersionLabel(e.target.value)}
              placeholder="e.g. 4.2"
              className="w-32 rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-slate-600">DPM file</span>
            <input
              ref={fileInput}
              type="file"
              accept=".accdb,.mdb"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-1.5 file:text-sm file:font-medium hover:file:bg-slate-200"
            />
          </label>

          <button
            type="button"
            onClick={() => void handleUpload()}
            disabled={!canUpload}
            className="rounded-md bg-slate-900 px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {progress === null ? 'Upload' : 'Uploading…'}
          </button>
        </div>

        {progress !== null && (
          <div className="mt-4">
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

        {uploadError && (
          <p className="mt-3 text-sm text-red-600">{uploadError}</p>
        )}
      </div>

      {/* Registry table */}
      <div className="mt-8">
        {loadError && (
          <p className="mb-3 text-sm text-red-600">
            Could not load snapshots: {loadError}
          </p>
        )}

        {snapshots.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-300 bg-white px-6 py-16 text-center">
            <p className="text-sm text-slate-400">No snapshots yet.</p>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs font-medium text-slate-500">
                  <th className="px-4 py-3">Version</th>
                  <th className="px-4 py-3">File</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Checksum</th>
                  <th className="px-4 py-3">Uploaded</th>
                </tr>
              </thead>
              <tbody>
                {snapshots.map((s) => (
                  <tr
                    key={s.id}
                    className="border-b border-slate-100 last:border-0"
                  >
                    <td className="px-4 py-3 font-medium text-slate-900">
                      {s.version_label}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {s.original_filename}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={s.status} />
                      {s.status === 'failed' && s.error && (
                        <span
                          className="ml-2 cursor-help text-xs text-red-500"
                          title={s.error}
                        >
                          (why?)
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-400">
                      {s.checksum.slice(0, 12)}…
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {formatDate(s.uploaded_at)}
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
