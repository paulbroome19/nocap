// API client for the taxonomy snapshot registry.

export type SnapshotStatus =
  | 'ingesting'
  | 'ready'
  | 'failed'
  | 'artifacts_missing'

export interface Regulator {
  id: number
  code: string
  name: string
}

export interface Snapshot {
  id: number
  regulator_id: number
  regulator_code: string
  regulator_name: string
  // Business name, e.g. "EBA Taxonomy 4.2".
  display_name: string
  version_label: string
  original_filename: string
  checksum: string
  status: SnapshotStatus
  error: string | null
  uploaded_at: string
  // Backend integrity only; not rendered as a UI panel.
  capabilities?: Capabilities | null
}

// A release is a container of typed artifact slots.
export type ReleaseSlotKind =
  | 'dpm_database'
  | 'taxonomy_package'
  | 'validation_rules'
  | 'filing_rules'
  | 'sample_files'

export type ArtifactStatus =
  | 'empty'
  | 'uploaded'
  | 'verifying'
  | 'ready'
  | 'failed'

export type Requirement = 'required' | 'formula' | 'register' | 'reference'

export interface ReleaseSlot {
  slot: ReleaseSlotKind
  label: string
  requirement: Requirement
  accept: string[]
  description: string
  status: ArtifactStatus
  filename: string | null
  checksum: string | null
  error: string | null
  uploaded_at: string | null
}

// Derived from which functional artifacts are ready (computed server-side).
export interface Capabilities {
  resolve: boolean
  generate: boolean
  verified_entry_points: boolean
  formula_validate: boolean
  rule_register: boolean
}

export interface ReleaseDetail {
  release: Snapshot
  ready: boolean
  slots: ReleaseSlot[]
  capabilities: Capabilities
  coherence_warnings: string[]
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

export async function listRegulators(): Promise<Regulator[]> {
  const res = await fetch('/api/taxonomy/regulators')
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function getRegulator(id: number): Promise<Regulator> {
  const res = await fetch(`/api/taxonomy/regulators/${id}`)
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function listRegulatorReleases(id: number): Promise<Snapshot[]> {
  const res = await fetch(`/api/taxonomy/regulators/${id}/releases`)
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function getSnapshot(id: number): Promise<Snapshot> {
  const res = await fetch(`/api/taxonomy/snapshots/${id}`)
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** Delete a release (blocked by the server if any run references it). */
export async function deleteRelease(id: number): Promise<void> {
  const res = await fetch(`/api/taxonomy/snapshots/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await parseError(res))
}

/** Rebuild the converted DB from the stored original — no re-upload. */
export async function reingestSnapshot(id: number): Promise<Snapshot> {
  const res = await fetch(`/api/taxonomy/snapshots/${id}/reingest`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** A release with its typed artifact slots + readiness. */
export async function getReleaseDetail(id: number): Promise<ReleaseDetail> {
  const res = await fetch(`/api/taxonomy/snapshots/${id}/artifacts`)
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** Upload a file into a slot (taxonomy package / filing rules / samples). */
export function uploadArtifact(
  id: number,
  slot: ReleaseSlotKind,
  file: File,
  onProgress?: (fraction: number) => void,
): Promise<ReleaseDetail> {
  return new Promise((resolve, reject) => {
    const form = new FormData()
    form.append('file', file)
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `/api/taxonomy/snapshots/${id}/artifacts/${slot}`)
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

export interface CreateReleaseFiles {
  dpm: File
  taxonomy: File
  rules: File
}

/**
 * Create a release from its three mandatory artifacts — all or nothing. The
 * server verifies each before persisting anything; a rejection surfaces its
 * plain-language reason. XHR is used so the (large) upload reports progress.
 * `onProgress` gets 0..1.
 */
export function createRelease(
  regulatorId: number,
  versionLabel: string,
  files: CreateReleaseFiles,
  onProgress?: (fraction: number) => void,
): Promise<Snapshot> {
  return new Promise((resolve, reject) => {
    const form = new FormData()
    form.append('version_label', versionLabel)
    form.append('regulator_id', String(regulatorId))
    form.append('dpm_file', files.dpm)
    form.append('taxonomy_file', files.taxonomy)
    form.append('rules_file', files.rules)

    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/taxonomy/releases')
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
