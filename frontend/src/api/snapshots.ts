// API client for the taxonomy snapshot registry.

export type SnapshotStatus =
  | 'ingesting'
  | 'ready'
  | 'failed'
  | 'artifacts_missing'

export interface Snapshot {
  id: number
  version_label: string
  original_filename: string
  checksum: string
  status: SnapshotStatus
  error: string | null
  uploaded_at: string
}

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json()
    return body?.error?.message ?? body?.detail ?? res.statusText
  } catch {
    return res.statusText
  }
}

export async function listSnapshots(): Promise<Snapshot[]> {
  const res = await fetch('/api/taxonomy/snapshots')
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function getSnapshot(id: number): Promise<Snapshot> {
  const res = await fetch(`/api/taxonomy/snapshots/${id}`)
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** Rebuild the converted DB from the stored original — no re-upload. */
export async function reingestSnapshot(id: number): Promise<Snapshot> {
  const res = await fetch(`/api/taxonomy/snapshots/${id}/reingest`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/**
 * Upload a DPM release. Uses XMLHttpRequest so we can report upload progress
 * (fetch has no upload-progress events). `onProgress` gets 0..1.
 */
export function uploadSnapshot(
  file: File,
  versionLabel: string,
  onProgress?: (fraction: number) => void,
): Promise<Snapshot> {
  return new Promise((resolve, reject) => {
    const form = new FormData()
    form.append('version_label', versionLabel)
    form.append('file', file)

    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/taxonomy/snapshots')

    xhr.upload.onprogress = (e) => {
      if (onProgress && e.lengthComputable) onProgress(e.loaded / e.total)
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText))
      } else {
        let message = xhr.statusText
        try {
          const body = JSON.parse(xhr.responseText)
          message = body?.error?.message ?? body?.detail ?? message
        } catch {
          /* keep statusText */
        }
        reject(new Error(message))
      }
    }
    xhr.onerror = () => reject(new Error('network error during upload'))
    xhr.send(form)
  })
}
