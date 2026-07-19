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
  Block,
  EmptyState,
  ErrorText,
  PageHeader,
  SectionLabel,
  Skeleton,
  secondaryBtn,
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

  return (
    <section>
      <PageHeader
        crumbs={[{ label: 'Reference Data', to: '/reference' }, { label: 'Filing Indicators' }]}
        title="Filing Indicators"
        subtitle="Per entity and reporting suite, declare each template Required, Optional (default, derived from facts), or Not required."
      />

      <SectionLabel>Target</SectionLabel>
      <Block className="mb-8 p-6">
        <EwcSelectors onChange={onChange} onNoRelease={onNoRelease} />
      </Block>

      <ErrorText>{error}</ErrorText>

      {!target ? (
        noRelease ? (
          <EmptyState>
            The selected regulator has no usable taxonomy release, so its
            templates can’t be listed. Add one under Taxonomies first.
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
          <div className="mb-2.5 flex items-center justify-between">
            <SectionLabel>Templates</SectionLabel>
            <div className="flex items-center gap-4">
              {saved && <span className="text-[13px] text-sub">Saved</span>}
              <button type="button" onClick={() => void save()} disabled={saving} className={secondaryBtn}>
                {saving ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
          <Block>
            {templates.map((t) => (
              <div
                key={t.code}
                className="flex items-center justify-between gap-4 border-t border-divider px-6 py-4 first:border-t-0"
              >
                <div className="min-w-0">
                  <span className="font-mono text-[13px] text-data">{t.code}</span>
                  <span className="ml-3 text-[13px] text-muted">{t.name}</span>
                </div>
                <DeclControl
                  value={declarations[t.code] ?? 'optional'}
                  onChange={(v) => setDecl(t.code, v)}
                  disabled={saving}
                />
              </div>
            ))}
          </Block>
        </>
      )}
    </section>
  )
}
