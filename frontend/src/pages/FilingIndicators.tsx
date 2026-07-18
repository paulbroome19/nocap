import { useCallback, useEffect, useState } from 'react'
import {
  getEntityWorkflowConfig,
  listWorkflowTemplates,
  updateEntityWorkflowConfig,
  type Declaration,
  type EntityWorkflowConfig,
  type TemplateInfo,
} from '../api/workflows'
import DeclControl from '../components/DeclControl'
import EwcSelectors, { type EwcTarget } from '../components/EwcSelectors'
import {
  Card,
  EmptyState,
  ErrorText,
  PageHeader,
  Skeleton,
  primaryBtn,
} from '../components/ui'

export default function FilingIndicators() {
  const [target, setTarget] = useState<EwcTarget | null>(null)
  const [noRelease, setNoRelease] = useState(false)
  const [config, setConfig] = useState<EntityWorkflowConfig | null>(null)
  const [templates, setTemplates] = useState<TemplateInfo[] | null>(null)
  const [declarations, setDeclarations] = useState<Record<string, Declaration>>({})
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)

  const onChange = useCallback((t: EwcTarget | null) => setTarget(t), [])
  const onNoRelease = useCallback((v: boolean) => setNoRelease(v), [])

  useEffect(() => {
    setSaved(false)
    if (!target) {
      setConfig(null)
      setTemplates(null)
      return
    }
    setTemplates(null)
    Promise.all([
      getEntityWorkflowConfig(target.entityId, target.workflowId),
      listWorkflowTemplates(target.workflowId, target.snapshotId),
    ])
      .then(([cfg, tmpl]) => {
        setConfig(cfg)
        setDeclarations({ ...cfg.indicator_declarations })
        setTemplates(tmpl)
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [target])

  function setDecl(code: string, v: Declaration) {
    setSaved(false)
    setDeclarations((prev) => {
      const next = { ...prev }
      if (v === 'optional') delete next[code]
      else next[code] = v
      return next
    })
  }

  async function save() {
    if (!target || !config) return
    setError(null)
    setSaving(true)
    try {
      // Preserve the parameters set on the other screen.
      await updateEntityWorkflowConfig(target.entityId, target.workflowId, {
        indicator_declarations: declarations,
        base_currency: config.base_currency,
        decimals: config.decimals,
      })
      setSaved(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  const declaredCount = Object.keys(declarations).length

  return (
    <section>
      <PageHeader
        crumbs={[
          { label: 'Reference Data', to: '/reference' },
          { label: 'Filing Indicators' },
        ]}
        title="Filing Indicators"
        subtitle="Per entity and reporting suite, declare each template Required, Optional (default, derived from facts), or Not required."
      />

      <Card className="mb-6 p-5">
        <EwcSelectors onChange={onChange} onNoRelease={onNoRelease} />
      </Card>

      <ErrorText>{error}</ErrorText>

      {!target ? (
        noRelease ? (
          <EmptyState>
            The selected regulator has no ready taxonomy release, so its
            templates can’t be listed. Onboard one under Taxonomies first.
          </EmptyState>
        ) : (
          <EmptyState>Choose an entity, regulator, and suite to begin.</EmptyState>
        )
      ) : templates === null ? (
        <Skeleton className="h-48" />
      ) : templates.length === 0 ? (
        <EmptyState>No templates in this suite.</EmptyState>
      ) : (
        <>
          <div className="mb-3 flex items-center justify-between">
            <p className="text-xs text-slate-400">
              {declaredCount} declared · {templates.length} templates
            </p>
            <div className="flex items-center gap-3">
              {saved && <span className="text-xs text-emerald-600">Saved</span>}
              <button
                type="button"
                onClick={() => void save()}
                disabled={saving}
                className={primaryBtn}
              >
                {saving ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
          <Card className="overflow-hidden">
            <table className="w-full text-sm">
              <tbody>
                {templates.map((t) => (
                  <tr
                    key={t.code}
                    className="border-b border-slate-100 last:border-0"
                  >
                    <td className="px-4 py-2.5">
                      <span className="font-mono text-xs text-slate-700">
                        {t.code}
                      </span>
                      <span className="ml-3 text-xs text-slate-400">{t.name}</span>
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <DeclControl
                        value={declarations[t.code] ?? 'optional'}
                        onChange={(v) => setDecl(t.code, v)}
                        disabled={saving}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </section>
  )
}
