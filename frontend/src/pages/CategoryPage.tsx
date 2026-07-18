import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { listCategorySuites, type SuiteSummary } from '../api/workflows'
import RunStatusBadge from '../components/RunStatusBadge'
import { CardSkeletons, EmptyState, ErrorText, PageHeader } from '../components/ui'

export default function CategoryPage() {
  const { category = '' } = useParams()
  const name = decodeURIComponent(category)
  const [suites, setSuites] = useState<SuiteSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setSuites(null)
    listCategorySuites(name)
      .then(setSuites)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [name])

  return (
    <section>
      <PageHeader
        title={name}
        crumbs={[{ label: 'Reporting', to: '/reporting' }, { label: name }]}
      />

      <ErrorText>{error}</ErrorText>

      {suites === null && !error ? (
        <CardSkeletons count={4} />
      ) : suites && suites.length === 0 ? (
        <EmptyState>No active suites in this category.</EmptyState>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {(suites ?? []).map((s) => (
            <Link
              key={s.id}
              to={`/reporting/suites/${s.id}`}
              className="group flex items-center justify-between gap-4 rounded-lg border border-slate-200 bg-white p-4 transition-all hover:border-slate-400 hover:shadow-sm"
            >
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-slate-900">
                  {s.name}
                </div>
                <div className="mt-0.5 font-mono text-xs text-slate-400">
                  {s.module_code}
                </div>
              </div>
              {s.last_run ? (
                <RunStatusBadge status={s.last_run.status} />
              ) : (
                <span className="shrink-0 text-xs text-slate-300">no runs</span>
              )}
            </Link>
          ))}
        </div>
      )}
    </section>
  )
}
