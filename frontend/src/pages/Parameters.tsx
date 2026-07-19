import { useCallback, useEffect, useState } from 'react'
import {
  getEntityWorkflowConfig,
  updateEntityWorkflowConfig,
  type EntityWorkflowConfig,
} from '../api/workflows'
import EwcSelectors, { type EwcTarget } from '../components/EwcSelectors'
import {
  Block,
  EmptyState,
  ErrorText,
  FieldLabel,
  PageHeader,
  SectionLabel,
  Skeleton,
  fieldClass,
  secondaryBtn,
} from '../components/ui'

export default function Parameters() {
  const [target, setTarget] = useState<EwcTarget | null>(null)
  const [config, setConfig] = useState<EntityWorkflowConfig | null>(null)
  const [baseCurrency, setBaseCurrency] = useState('')
  const [decimals, setDecimals] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)

  const onChange = useCallback((t: EwcTarget | null) => setTarget(t), [])

  useEffect(() => {
    setSaved(false)
    if (!target) {
      setConfig(null)
      return
    }
    setConfig(null)
    getEntityWorkflowConfig(target.entityId, target.workflowId)
      .then((cfg) => {
        setConfig(cfg)
        setBaseCurrency(cfg.base_currency ?? '')
        setDecimals(cfg.decimals === null ? '' : String(cfg.decimals))
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [target])

  async function save() {
    if (!target || !config) return
    setError(null)
    setSaving(true)
    try {
      // Preserve the filing-indicator declarations set on the other screen.
      await updateEntityWorkflowConfig(target.entityId, target.workflowId, {
        indicator_declarations: config.indicator_declarations,
        base_currency: baseCurrency.trim() || null,
        decimals: decimals.trim() === '' ? null : Number(decimals),
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
        crumbs={[
          { label: 'Reference Data', to: '/reference' },
          { label: 'Parameters' },
        ]}
        title="Parameters"
        subtitle="Per entity and reporting suite, set the reporting currency and decimals. Blank uses the defaults."
      />

      <SectionLabel>Target</SectionLabel>
      <Block className="mb-8 p-6">
        <EwcSelectors onChange={onChange} />
      </Block>

      <ErrorText>{error}</ErrorText>

      {!target ? (
        <EmptyState>Choose an entity, regulator, and suite to begin.</EmptyState>
      ) : config === null ? (
        <Skeleton className="h-32" />
      ) : (
        <>
          <SectionLabel>Package parameters</SectionLabel>
          <Block className="mt-2.5 space-y-5 p-6">
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block">
                <FieldLabel>Base currency</FieldLabel>
                <input
                  type="text"
                  value={baseCurrency}
                  onChange={(e) => {
                    setBaseCurrency(e.target.value.toUpperCase())
                    setSaved(false)
                  }}
                  placeholder="EUR (default)"
                  maxLength={3}
                  className={`${fieldClass} font-mono uppercase`}
                />
              </label>
              <label className="block">
                <FieldLabel>Decimals</FieldLabel>
                <input
                  type="number"
                  value={decimals}
                  onChange={(e) => {
                    setDecimals(e.target.value)
                    setSaved(false)
                  }}
                  placeholder="-3 (default)"
                  className={`${fieldClass} font-mono`}
                />
              </label>
            </div>
            <div className="flex items-center gap-4">
              <button
                type="button"
                onClick={() => void save()}
                disabled={saving}
                className={secondaryBtn}
              >
                {saving ? 'Saving…' : 'Save'}
              </button>
              {saved && <span className="text-[13px] text-sub">Saved</span>}
            </div>
          </Block>
        </>
      )}
    </section>
  )
}
