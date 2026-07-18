import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listConfigs, type WorkflowConfig } from '../api/workflows'
import { EmptyState, ErrorText, Loading, PageHeader } from '../components/ui'

export default function Reporting() {
  const [configs, setConfigs] = useState<WorkflowConfig[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listConfigs()
      .then(setConfigs)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  // Group by framework for a tidy, scannable list.
  const byFramework = (configs ?? []).reduce<Record<string, WorkflowConfig[]>>(
    (acc, c) => {
      ;(acc[c.framework_code] ??= []).push(c)
      return acc
    },
    {},
  )

  return (
    <section>
      <PageHeader
        title="Reporting"
        subtitle="Configured reporting suites. Select one to start a new run or browse its history."
      />

      <ErrorText>{error}</ErrorText>

      {configs === null && !error ? (
        <Loading />
      ) : configs && configs.length === 0 ? (
        <EmptyState>No workflows configured.</EmptyState>
      ) : (
        <div className="space-y-8">
          {Object.entries(byFramework).map(([framework, items]) => (
            <div key={framework}>
              <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                {framework}
              </h2>
              <div className="mt-2 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {items.map((c) => (
                  <Link
                    key={c.id}
                    to={`/reporting/workflows/${c.id}`}
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
      )}
    </section>
  )
}
