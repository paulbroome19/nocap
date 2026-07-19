import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { listRegulators } from '../api/snapshots'
import {
  listConfigs,
  updateWorkflowSettings,
  type WorkflowConfig,
} from '../api/workflows'
import {
  Block,
  ErrorText,
  PageHeader,
  SectionLabel,
  Select,
  TableSkeleton,
} from '../components/ui'
import { CATEGORY_ORDER } from '../lib/categories'

function Toggle({ on, onChange }: { on: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={() => onChange(!on)}
      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
        on ? 'bg-ink' : 'bg-field'
      }`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
          on ? 'translate-x-4' : 'translate-x-0.5'
        }`}
      />
    </button>
  )
}

export default function SettingsActiveReporting() {
  const { regulatorCode = '' } = useParams()
  const [regName, setRegName] = useState('')
  const [configs, setConfigs] = useState<WorkflowConfig[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState<number | null>(null)

  useEffect(() => {
    listRegulators()
      .then((rs) => setRegName(rs.find((r) => r.code === regulatorCode)?.name ?? ''))
      .catch(() => {})
    listConfigs(true)
      .then(setConfigs)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [regulatorCode])

  async function persist(wf: WorkflowConfig, patch: Partial<WorkflowConfig>) {
    const next = { ...wf, ...patch }
    setConfigs((cs) => cs?.map((c) => (c.id === wf.id ? next : c)) ?? null)
    setSaving(wf.id)
    try {
      const saved = await updateWorkflowSettings(wf.id, {
        category: next.category,
        is_active: next.is_active,
      })
      setConfigs((cs) => cs?.map((c) => (c.id === wf.id ? saved : c)) ?? null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setConfigs((cs) => cs?.map((c) => (c.id === wf.id ? wf : c)) ?? null)
    } finally {
      setSaving(null)
    }
  }

  return (
    <section>
      <PageHeader
        crumbs={[
          { label: 'Settings', to: '/settings' },
          { label: 'Reporting', to: '/settings/reporting' },
          { label: regName || regulatorCode },
        ]}
        title="Active reporting"
        subtitle="Which suites appear in Reporting, and their category."
      />
      <ErrorText>{error}</ErrorText>

      <SectionLabel>Suite</SectionLabel>
      {configs === null && !error ? (
        <TableSkeleton />
      ) : (
        <Block>
          {(configs ?? []).map((wf) => (
            <div
              key={wf.id}
              className="flex items-center justify-between gap-6 border-t border-divider px-6 py-[18px] first:border-t-0"
            >
              <div className="min-w-0 flex-1">
                <div className="truncate text-[15px] font-semibold text-ink">{wf.name}</div>
              </div>
              <Select
                value={wf.category ?? ''}
                disabled={saving === wf.id}
                onChange={(v) => void persist(wf, { category: v || null })}
                className="w-56 shrink-0"
              >
                <option value="">Uncategorised</option>
                {CATEGORY_ORDER.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </Select>
              <Toggle on={wf.is_active} onChange={(v) => void persist(wf, { is_active: v })} />
            </div>
          ))}
        </Block>
      )}
    </section>
  )
}
