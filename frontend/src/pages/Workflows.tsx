import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listConfigs, type WorkflowConfig } from '../api/workflows'

export default function Workflows() {
  const [configs, setConfigs] = useState<WorkflowConfig[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listConfigs()
      .then(setConfigs)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  // Group by framework for a tidy, scannable list.
  const byFramework = configs.reduce<Record<string, WorkflowConfig[]>>((acc, c) => {
    ;(acc[c.framework_code] ??= []).push(c)
    return acc
  }, {})

  return (
    <section>
      <h1 className="text-2xl font-semibold tracking-tight">Workflows</h1>
      <p className="mt-1 text-sm text-slate-500">
        Configured reporting suites. Select one to start a new run.
      </p>

      {error && <p className="mt-4 text-sm text-red-600">{error}</p>}

      <div className="mt-6 space-y-8">
        {Object.entries(byFramework).map(([framework, items]) => (
          <div key={framework}>
            <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
              {framework}
            </h2>
            <div className="mt-2 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {items.map((c) => (
                <Link
                  key={c.id}
                  to={`/workflows/${c.id}`}
                  className="group rounded-lg border border-slate-200 bg-white p-4 transition-colors hover:border-slate-400"
                >
                  <div className="text-sm font-medium text-slate-900 group-hover:text-slate-700">
                    {c.name}
                  </div>
                  <div className="mt-1 font-mono text-xs text-slate-400">
                    {c.module_code}
                  </div>
                </Link>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
