// API client for the workflows (runs) surface.

export interface WorkflowConfig {
  id: number
  name: string
  framework_code: string
  module_code: string
  active: boolean
}

export type RunStatus =
  | 'created'
  | 'files_attached'
  | 'running'
  | 'generated'
  | 'failed_validation'
  | 'failed'

export type Severity = 'error' | 'warning' | 'info'

export interface Finding {
  id: number
  severity: Severity
  phase: string
  code: string
  message: string
  file: string | null
  sheet: string | null
  row: number | null
  template_code: string | null
  row_code: string | null
  column_code: string | null
}

export interface Run {
  id: number
  workflow_id: number
  snapshot_id: number
  release_id: number
  reference_date: string
  entity_lei: string
  entity_scope: string
  country: string
  status: RunStatus
  error: string | null
  failure_details: Array<Record<string, unknown>> | null
  created_at: string
}

export interface RunFile {
  id: number
  run_id: number
  role: string
  filename: string
  checksum: string
  created_at: string
}

export interface RunDetail {
  run: Run
  files: RunFile[]
  findings: Finding[]
}

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json()
    return body?.error?.message ?? body?.detail ?? res.statusText
  } catch {
    return res.statusText
  }
}

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

async function postJSON<T>(url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

async function postFile<T>(url: string, file: File): Promise<T> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(url, { method: 'POST', body: form })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export const listConfigs = () =>
  getJSON<WorkflowConfig[]>('/api/workflows/configs')

export const runHistory = (workflowId: number) =>
  getJSON<Run[]>(`/api/workflows/configs/${workflowId}/runs`)

export interface CreateRunBody {
  workflow_id: number
  snapshot_id: number
  reference_date: string
  entity_lei: string
  entity_scope: string
}

export const createRun = (body: CreateRunBody) =>
  postJSON<Run>('/api/workflows/runs', body)

export const attachFactFile = (runId: number, file: File) =>
  postFile(`/api/workflows/runs/${runId}/fact-file`, file)

export const attachIndicatorsFile = (runId: number, file: File) =>
  postFile(`/api/workflows/runs/${runId}/indicators-params-file`, file)

export const executeRun = (runId: number) =>
  postJSON<Run>(`/api/workflows/runs/${runId}/execute`)

export const getRunDetail = (runId: number) =>
  getJSON<RunDetail>(`/api/workflows/runs/${runId}`)

export const runFileDownloadUrl = (runFileId: number) =>
  `/api/workflows/run-files/${runFileId}/download`
