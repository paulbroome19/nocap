// API client for the workflows (reporting) surface.

export interface WorkflowConfig {
  id: number
  name: string
  framework_code: string
  module_code: string
  category: string | null
  is_active: boolean
}

export interface RunSummary {
  id: number
  reference_date: string
  status: RunStatus
  created_at: string
}

export interface Category {
  category: string
  active_count: number
  last_run: RunSummary | null
}

export interface SuiteSummary extends WorkflowConfig {
  last_run: RunSummary | null
}

export interface Entity {
  id: number
  name: string
  lei: string
  country: string
  default_scope: string
}

export interface EntityWrite {
  name: string
  lei: string
  country: string
  default_scope: string
}

export interface TemplateInfo {
  code: string
  name: string
}

/** A template's filing-indicator declaration. "optional" is the default and is
 *  represented by the absence of a key. */
export type Declaration = 'optional' | 'required' | 'not_required'

export interface EntityWorkflowConfig {
  entity_id: number
  workflow_id: number
  indicator_declarations: Record<string, 'required' | 'not_required'>
  base_currency: string | null
  decimals: number | null
}

export interface EntityWorkflowConfigWrite {
  indicator_declarations: Record<string, Declaration>
  base_currency: string | null
  decimals: number | null
}

export type RunStatus =
  | 'created'
  | 'files_attached'
  | 'running'
  | 'formula_validation_running'
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

export interface FilingIndicatorOutcome {
  template_code: string
  reported: boolean
  source: 'declared' | 'auto'
}

export interface RuleEvaluation {
  message: string
  values: string | null
  template_code?: string | null
  row_code?: string | null
  column_code?: string | null
}

export interface RegisterRow {
  id: string
  rule: string
  source: 'structural' | 'formula'
  template: string | null
  data_evaluated: string
  result: 'PASSED' | 'FAILED' | 'WARNING' | 'NOTE' | 'DEACTIVATED'
  detail: string
  // The human rule statement (workbook Description); formula rows only.
  rule_text?: string | null
  // Plain-English provenance (structural checks): what was checked and why.
  description?: string | null
  // Display severity: 'error' | 'warning' | 'info' | null (unknown).
  severity?: string | null
  // A FAILED row that blocks submission (error severity).
  blocking?: boolean
  // Per-evaluation detail for formula rows (individual failing contexts).
  evaluations?: RuleEvaluation[] | null
  satisfied?: number | null
  not_satisfied?: number | null
}

export interface Verdict {
  label: string // Submittable | Not submittable | Validating | Run failed
  submittable: boolean | null // null while validation is still in progress
  blocking: number
  non_blocking_failures: number
  warnings: number
  unknown_severity: number
  severity_known: boolean
  reasoning: string
  status: string
}

export interface FormulaSummary {
  status: 'executed' | 'unavailable' | 'not_run'
  loaded?: number
  evaluated?: number
  satisfied?: number
  unsatisfied: number
  deactivated: string[]
  note: string | null
}

export interface FactRow {
  template_code: string
  row_code: string
  column_code: string
  value: string
  source_sheet: string | null
  source_row: number | null
}

export interface Run {
  id: number
  workflow_id: number
  snapshot_id: number
  release_id: number
  reference_date: string
  entity_id: number | null
  // Entity values frozen at execution — render these, never the live entity.
  entity_name: string | null
  entity_lei: string
  entity_scope: string
  country: string
  snapshot_key: string | null
  adjusted_key: string | null
  version_key: string | null
  base_currency: string
  decimals: number
  status: RunStatus
  error: string | null
  failure_details: Array<Record<string, unknown>> | null
  // The taxonomy version this run was executed against (the bound release),
  // frozen at creation — the primary version label; module_version is detail.
  taxonomy_version: string | null
  module_version: string | null
  framework_version: string | null
  // The version's reference-date applicability window, frozen at creation.
  module_valid_from: string | null
  module_valid_to: string | null
  // The validation-rule set applied, frozen when validation ran.
  rule_scope: RuleScope | null
  created_at: string
}

export interface RuleScope {
  count: number
  taxonomy_version: string | null
  module_code: string | null
  module_version: string | null
  framework_version: string | null
  reference_date: string
}

export interface RunFile {
  id: number
  run_id: number
  role: string
  filename: string
  checksum: string
  created_at: string
  available: boolean
  size_bytes: number | null
}

export interface RunDetail {
  run: Run
  files: RunFile[]
  findings: Finding[]
  fact_count: number
  filing_indicators: FilingIndicatorOutcome[] | null
  rule_register: RegisterRow[]
  formula_summary: FormulaSummary | null
  verdict: Verdict
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

async function sendJSON<T>(
  method: 'POST' | 'PUT' | 'PATCH',
  url: string,
  body?: unknown,
): Promise<T> {
  const res = await fetch(url, {
    method,
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

// --- workflows / categories ------------------------------------------------

export const listConfigs = (includeInactive = false) =>
  getJSON<WorkflowConfig[]>(
    `/api/workflows/configs${includeInactive ? '?include_inactive=true' : ''}`,
  )

export const listCategories = () =>
  getJSON<Category[]>('/api/workflows/categories')

export const listCategorySuites = (category: string) =>
  getJSON<SuiteSummary[]>(
    `/api/workflows/categories/${encodeURIComponent(category)}/suites`,
  )

export const getConfig = (id: number) =>
  listConfigs(true).then((cs) => cs.find((c) => c.id === id) ?? null)

export const updateWorkflowSettings = (
  id: number,
  body: { category: string | null; is_active: boolean },
) => sendJSON<WorkflowConfig>('PATCH', `/api/workflows/configs/${id}`, body)

// --- entities & per-workflow config ----------------------------------------

export const listEntities = () => getJSON<Entity[]>('/api/workflows/entities')

export const getEntity = (id: number) =>
  getJSON<Entity>(`/api/workflows/entities/${id}`)

export const createEntity = (body: EntityWrite) =>
  sendJSON<Entity>('POST', '/api/workflows/entities', body)

export const updateEntity = (id: number, body: EntityWrite) =>
  sendJSON<Entity>('PUT', `/api/workflows/entities/${id}`, body)

/** Delete an entity (live reference data). Runs keep their frozen values. */
export async function deleteEntity(id: number): Promise<void> {
  const res = await fetch(`/api/workflows/entities/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await parseError(res))
}

export const getEntityWorkflowConfig = (entityId: number, workflowId: number) =>
  getJSON<EntityWorkflowConfig>(
    `/api/workflows/entities/${entityId}/configs/${workflowId}`,
  )

export const updateEntityWorkflowConfig = (
  entityId: number,
  workflowId: number,
  body: EntityWorkflowConfigWrite,
) =>
  sendJSON<EntityWorkflowConfig>(
    'PUT',
    `/api/workflows/entities/${entityId}/configs/${workflowId}`,
    body,
  )

export const listWorkflowTemplates = (workflowId: number, snapshotId: number) =>
  getJSON<TemplateInfo[]>(
    `/api/workflows/configs/${workflowId}/templates?snapshot_id=${snapshotId}`,
  )

// --- runs ------------------------------------------------------------------

export const runHistory = (workflowId: number) =>
  getJSON<Run[]>(`/api/workflows/configs/${workflowId}/runs`)

/** One selectable taxonomy version for a suite's module — a distinct
 *  (module_version, framework_version) across all ready releases. The dropdown
 *  shows module_version; the rest is supporting detail. A run binds to
 *  snapshot_id (the newest release providing this version). */
export interface ModuleVersionOption {
  module_code: string
  module_name: string | null
  module_version: string
  framework_version: string
  snapshot_id: number
  valid_from: string | null
  valid_to: string | null
  // Release version labels providing this option, oldest first (e.g.
  // ["4.2", "4.2.1"]) — the primary label of the option.
  taxonomy_versions: string[]
}

export interface ModuleVersionOptions {
  workflow_id: number
  module_code: string
  options: ModuleVersionOption[]
}

export const listModuleVersions = (workflowId: number) =>
  getJSON<ModuleVersionOptions>(
    `/api/workflows/configs/${workflowId}/module-versions`,
  )

/** The ingestion summary: per enabled suite, what a release provides. */
export interface ReleaseProvision {
  module_code: string
  module_name: string | null
  workflow_name: string
  module_version: string | null
  framework_version: string | null
  is_new: boolean
  already_from: string | null // the taxonomy version it was first available from
}

export interface ReleaseProvisionsSummary {
  snapshot_id: number
  // The release's own taxonomy version (e.g. "4.2.1") — shown on every row.
  taxonomy_version: string
  // No earlier release loaded → suppress the NEW badge (nothing to compare).
  is_first_release: boolean
  provisions: ReleaseProvision[]
}

export const getReleaseProvisions = (snapshotId: number) =>
  getJSON<ReleaseProvisionsSummary>(
    `/api/workflows/releases/${snapshotId}/provisions`,
  )

export interface CreateRunBody {
  workflow_id: number
  snapshot_id: number
  reference_date: string
  entity_id: number
  snapshot_key?: string
  adjusted_key?: string
  version_key?: string
}

export const createRun = (body: CreateRunBody) =>
  sendJSON<Run>('POST', '/api/workflows/runs', body)

/** One live-dependency change detected before a re-execution. */
export interface DependencyChange {
  kind: string
  message: string
  fields?: string[]
}

/** Thrown by {@link reexecuteRun} when the entity or release changed and the
 *  caller has not yet acknowledged; carries the changes to show the user. */
export class DependencyChangedError extends Error {
  changes: DependencyChange[]
  constructor(message: string, changes: DependencyChange[]) {
    super(message)
    this.name = 'DependencyChangedError'
    this.changes = changes
  }
}

/** How to resolve a changed dependency when re-executing. */
export interface ReexecuteOptions {
  acknowledge?: boolean // proceed with a still-usable changed dependency
  entityId?: number // choose a replacement entity (for a deleted entity)
  releaseSnapshotId?: number // choose a replacement release (for a deleted one)
}

/**
 * Re-execute / resubmit an existing instance (full resubmission). Creates a new
 * run carrying the source run's instance identity; the caller then attaches a
 * fact file and executes it.
 *
 * If the entity or taxonomy release has changed since the last execution, the
 * server responds 409 and this throws {@link DependencyChangedError} with the
 * list of changes — never re-binding silently. Retry with a replacement
 * (`entityId` / `releaseSnapshotId`) or, for a still-usable change,
 * `acknowledge: true`.
 */
export async function reexecuteRun(
  runId: number,
  opts: ReexecuteOptions = {},
): Promise<Run> {
  const res = await fetch(`/api/workflows/runs/${runId}/reexecute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      acknowledge_changes: opts.acknowledge ?? false,
      entity_id: opts.entityId ?? null,
      release_snapshot_id: opts.releaseSnapshotId ?? null,
    }),
  })
  if (res.status === 409) {
    const body = await res.json().catch(() => null)
    if (body?.error?.code === 'dependency_changed') {
      throw new DependencyChangedError(
        body.error.message ?? 'Dependencies changed',
        (body.error.details ?? []) as DependencyChange[],
      )
    }
    throw new Error(body?.error?.message ?? res.statusText)
  }
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

/** Delete an execution and its artifacts. Other executions are untouched. */
export async function deleteRun(runId: number): Promise<void> {
  const res = await fetch(`/api/workflows/runs/${runId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(await parseError(res))
}

export const attachFactFile = (runId: number, file: File) =>
  postFile(`/api/workflows/runs/${runId}/fact-file`, file)

export const executeRun = (runId: number) =>
  sendJSON<Run>('POST', `/api/workflows/runs/${runId}/execute`)

export const getRunDetail = (runId: number) =>
  getJSON<RunDetail>(`/api/workflows/runs/${runId}`)

export const getRunFacts = (runId: number) =>
  getJSON<FactRow[]>(`/api/workflows/runs/${runId}/facts`)

export const runFileDownloadUrl = (runFileId: number) =>
  `/api/workflows/run-files/${runFileId}/download`

/**
 * Download a run file gracefully: fetch it, and on error surface the server's
 * message (instead of navigating the browser to a JSON error page). On success
 * it triggers a normal browser download from the blob.
 */
export async function downloadRunFile(
  runFileId: number,
  filename: string,
): Promise<void> {
  const res = await fetch(runFileDownloadUrl(runFileId))
  if (!res.ok) throw new Error(await parseError(res))
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
