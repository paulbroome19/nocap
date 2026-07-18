import { useEffect, useState } from 'react'
import {
  listConfigs,
  updateWorkflowSettings,
  type WorkflowConfig,
} from '../api/workflows'
import { Card, ErrorText, Loading } from '../components/ui'

const CATEGORIES = ['Liquidity', 'Capital', 'Financial', 'Last Mile Reporting']

function Toggle({
  on,
  onChange,
}: {
  on: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={() => onChange(!on)}
      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
        on ? 'bg-slate-900' : 'bg-slate-200'
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

export default function Settings() {
  const [configs, setConfigs] = useState<WorkflowConfig[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState<number | null>(null)

  useEffect(() => {
    listConfigs(true)
      .then(setConfigs)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  async function persist(wf: WorkflowConfig, patch: Partial<WorkflowConfig>) {
    const next = { ...wf, ...patch }
    // Optimistic update.
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
      // Roll back on failure.
      setConfigs((cs) => cs?.map((c) => (c.id === wf.id ? wf : c)) ?? null)
    } finally {
      setSaving(null)
    }
  }

  return (
    <section>
      <h1 className="mb-6 text-2xl font-semibold tracking-tight text-slate-900">
        Settings
      </h1>

      <ErrorText>{error}</ErrorText>

      <div>
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
          Active Reporting
        </h2>
        {configs === null && !error ? (
          <Loading />
        ) : (
          <Card className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs font-medium text-slate-500">
                  <th className="px-4 py-3">Suite</th>
                  <th className="px-4 py-3">Category</th>
                  <th className="px-4 py-3 text-right">Active</th>
                </tr>
              </thead>
              <tbody>
                {(configs ?? []).map((wf) => (
                  <tr
                    key={wf.id}
                    className="border-b border-slate-100 last:border-0"
                  >
                    <td className="px-4 py-3">
                      <div className="font-medium text-slate-900">{wf.name}</div>
                      <div className="font-mono text-xs text-slate-400">
                        {wf.module_code}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <select
                        value={wf.category ?? ''}
                        disabled={saving === wf.id}
                        onChange={(e) =>
                          void persist(wf, {
                            category: e.target.value || null,
                          })
                        }
                        className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-sm text-slate-800 focus:border-slate-500 focus:outline-none"
                      >
                        <option value="">Uncategorised</option>
                        {CATEGORIES.map((c) => (
                          <option key={c} value={c}>
                            {c}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end">
                        <Toggle
                          on={wf.is_active}
                          onChange={(v) => void persist(wf, { is_active: v })}
                        />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </div>
    </section>
  )
}
