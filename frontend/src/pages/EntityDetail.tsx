import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { listSnapshots, type Snapshot } from '../api/snapshots'
import {
  getEntity,
  getEntityWorkflowConfig,
  listConfigs,
  listWorkflowTemplates,
  updateEntity,
  updateEntityWorkflowConfig,
  type Declaration,
  type Entity,
  type TemplateInfo,
  type WorkflowConfig,
} from '../api/workflows'
import EntityForm from '../components/EntityForm'
import {
  Card,
  EmptyState,
  ErrorText,
  Loading,
  PageHeader,
  fieldClass,
  primaryBtn,
  secondaryBtn,
} from '../components/ui'

const DECL_OPTIONS: { v: Declaration; label: string }[] = [
  { v: 'auto', label: 'Auto' },
  { v: 'true', label: 'File: true' },
  { v: 'false', label: 'File: false' },
]

const DECL_ACTIVE: Record<Declaration, string> = {
  auto: 'bg-slate-900 text-white',
  true: 'bg-emerald-600 text-white',
  false: 'bg-amber-500 text-white',
}

function DeclControl({
  value,
  onChange,
}: {
  value: Declaration
  onChange: (v: Declaration) => void
}) {
  return (
    <div className="inline-flex overflow-hidden rounded-md border border-slate-300">
      {DECL_OPTIONS.map((o, i) => (
        <button
          key={o.v}
          type="button"
          onClick={() => onChange(o.v)}
          className={[
            'px-2.5 py-1 text-xs font-medium transition-colors',
            i > 0 ? 'border-l border-slate-300' : '',
            value === o.v
              ? DECL_ACTIVE[o.v]
              : 'bg-white text-slate-600 hover:bg-slate-50',
          ].join(' ')}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

export default function EntityDetail() {
  const { entityId } = useParams()
  const id = Number(entityId)

  const [entity, setEntity] = useState<Entity | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)

  const [workflows, setWorkflows] = useState<WorkflowConfig[]>([])
  const [releases, setReleases] = useState<Snapshot[]>([])

  const loadEntity = useCallback(() => {
    getEntity(id)
      .then(setEntity)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [id])

  useEffect(() => {
    loadEntity()
    listConfigs().then(setWorkflows).catch(() => {})
    listSnapshots()
      .then((s) => setReleases(s.filter((x) => x.status === 'ready')))
      .catch(() => {})
  }, [loadEntity])

  if (error) return <ErrorText>{error}</ErrorText>
  if (!entity) return <Loading />

  const meta: [string, string][] = [
    ['LEI', entity.lei],
    ['Country', entity.country],
    ['Default scope', entity.default_scope],
  ]

  return (
    <section>
      <PageHeader
        back={{ to: '/reference', label: 'Reference Data' }}
        title={entity.name}
        actions={
          !editing && (
            <button
              type="button"
              className={secondaryBtn}
              onClick={() => setEditing(true)}
            >
              Edit
            </button>
          )
        }
      />

      {editing ? (
        <Card className="mb-8 p-5">
          <h2 className="mb-4 text-sm font-semibold text-slate-900">
            Edit entity
          </h2>
          <EntityForm
            initial={entity}
            submitLabel="Save changes"
            onCancel={() => setEditing(false)}
            onSubmit={async (body) => {
              const updated = await updateEntity(id, body)
              setEntity(updated)
              setEditing(false)
            }}
          />
        </Card>
      ) : (
        <Card className="mb-8 p-5">
          <dl className="grid grid-cols-3 gap-6 text-sm">
            {meta.map(([k, v]) => (
              <div key={k}>
                <dt className="text-xs text-slate-400">{k}</dt>
                <dd className="mt-0.5 font-mono text-slate-800">{v}</dd>
              </div>
            ))}
          </dl>
        </Card>
      )}

      <WorkflowConfigSection
        entityId={id}
        workflows={workflows}
        releases={releases}
      />
    </section>
  )
}

function WorkflowConfigSection({
  entityId,
  workflows,
  releases,
}: {
  entityId: number
  workflows: WorkflowConfig[]
  releases: Snapshot[]
}) {
  const [workflowId, setWorkflowId] = useState<number | ''>('')
  const [releaseId, setReleaseId] = useState<number | ''>('')

  const [templates, setTemplates] = useState<TemplateInfo[] | null>(null)
  const [declarations, setDeclarations] = useState<Record<string, Declaration>>({})
  const [baseCurrency, setBaseCurrency] = useState('')
  const [decimals, setDecimals] = useState('')

  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveState, setSaveState] = useState<string | null>(null)

  // Load the (entity, workflow) config + the module's templates once both a
  // workflow and a release are chosen.
  useEffect(() => {
    if (workflowId === '' || releaseId === '') {
      setTemplates(null)
      return
    }
    setLoading(true)
    setLoadError(null)
    setSaveState(null)
    Promise.all([
      getEntityWorkflowConfig(entityId, workflowId),
      listWorkflowTemplates(workflowId, releaseId),
    ])
      .then(([config, tmpls]) => {
        setTemplates(tmpls)
        setDeclarations({ ...config.indicator_declarations })
        setBaseCurrency(config.base_currency ?? '')
        setDecimals(config.decimals === null ? '' : String(config.decimals))
      })
      .catch((e) => {
        setLoadError(e instanceof Error ? e.message : String(e))
        setTemplates(null)
      })
      .finally(() => setLoading(false))
  }, [entityId, workflowId, releaseId])

  function setDecl(code: string, v: Declaration) {
    setSaveState(null)
    setDeclarations((prev) => {
      const next = { ...prev }
      if (v === 'auto') delete next[code]
      else next[code] = v
      return next
    })
  }

  async function save() {
    if (workflowId === '') return
    setSaveState('Saving…')
    try {
      await updateEntityWorkflowConfig(entityId, workflowId, {
        indicator_declarations: declarations,
        base_currency: baseCurrency.trim() || null,
        decimals: decimals.trim() === '' ? null : Number(decimals),
      })
      setSaveState('Saved')
    } catch (e) {
      setSaveState(e instanceof Error ? e.message : String(e))
    }
  }

  const declaredCount = Object.keys(declarations).length

  return (
    <div>
      <h2 className="text-sm font-semibold text-slate-900">
        Per-workflow configuration
      </h2>
      <p className="mt-1 text-sm text-slate-500">
        Filing-indicator declarations and parameter overrides for this entity.
        Declarations default to <span className="font-medium">Auto</span> (report
        a template only when it has facts).
      </p>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-slate-600">Workflow</span>
          <select
            className={fieldClass}
            value={workflowId}
            onChange={(e) =>
              setWorkflowId(e.target.value === '' ? '' : Number(e.target.value))
            }
          >
            <option value="">Select…</option>
            {workflows.map((w) => (
              <option key={w.id} value={w.id}>
                {w.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-slate-600">
            Release (for template list)
          </span>
          <select
            className={fieldClass}
            value={releaseId}
            onChange={(e) =>
              setReleaseId(e.target.value === '' ? '' : Number(e.target.value))
            }
          >
            <option value="">Select…</option>
            {releases.map((r) => (
              <option key={r.id} value={r.id}>
                {r.version_label} — {r.original_filename}
              </option>
            ))}
          </select>
        </label>
      </div>

      {releases.length === 0 && (
        <p className="mt-3 text-sm text-amber-700">
          No ready releases — onboard one to configure filing indicators.
        </p>
      )}

      <div className="mt-6">
        <ErrorText>{loadError}</ErrorText>
        {loading && <Loading />}

        {workflowId !== '' && releaseId !== '' && !loading && !loadError && (
          <>
            {/* Parameter overrides */}
            <Card className="p-5">
              <h3 className="text-sm font-semibold text-slate-900">
                Parameter overrides
              </h3>
              <p className="mt-0.5 text-xs text-slate-500">
                Used as defaults when a run is created. Leave blank for the
                system defaults.
              </p>
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <label className="flex flex-col gap-1">
                  <span className="text-xs font-medium text-slate-600">
                    Base currency
                  </span>
                  <input
                    className={`${fieldClass} font-mono uppercase`}
                    value={baseCurrency}
                    maxLength={3}
                    placeholder="EUR (default)"
                    onChange={(e) => {
                      setSaveState(null)
                      setBaseCurrency(e.target.value)
                    }}
                  />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-xs font-medium text-slate-600">
                    Decimals
                  </span>
                  <input
                    type="number"
                    className={fieldClass}
                    value={decimals}
                    placeholder="-3 (default)"
                    onChange={(e) => {
                      setSaveState(null)
                      setDecimals(e.target.value)
                    }}
                  />
                </label>
              </div>
            </Card>

            {/* Filing indicator declarations */}
            <Card className="mt-4 overflow-hidden">
              <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
                <h3 className="text-sm font-semibold text-slate-900">
                  Filing indicator declarations
                </h3>
                <span className="text-xs text-slate-400">
                  {declaredCount} declared · {templates?.length ?? 0} templates
                </span>
              </div>
              {templates && templates.length === 0 ? (
                <div className="px-5 py-6">
                  <EmptyState>No templates in this module.</EmptyState>
                </div>
              ) : (
                <table className="w-full text-sm">
                  <tbody>
                    {(templates ?? []).map((t) => (
                      <tr
                        key={t.code}
                        className="border-b border-slate-100 last:border-0"
                      >
                        <td className="px-5 py-2.5">
                          <div className="font-mono text-xs text-slate-800">
                            {t.code}
                          </div>
                          <div className="text-xs text-slate-400">{t.name}</div>
                        </td>
                        <td className="px-5 py-2.5 text-right">
                          <DeclControl
                            value={declarations[t.code] ?? 'auto'}
                            onChange={(v) => setDecl(t.code, v)}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </Card>

            <div className="mt-4 flex items-center gap-3">
              <button type="button" className={primaryBtn} onClick={() => void save()}>
                Save configuration
              </button>
              {saveState && (
                <span
                  className={
                    saveState === 'Saved'
                      ? 'text-sm text-emerald-700'
                      : 'text-sm text-slate-500'
                  }
                >
                  {saveState}
                </span>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
