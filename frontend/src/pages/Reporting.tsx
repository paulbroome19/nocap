import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listCategories, type Category } from '../api/workflows'
import RunStatusBadge from '../components/RunStatusBadge'
import { CardSkeletons, ErrorText } from '../components/ui'

function formatDate(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString(undefined, {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      })
}

export default function Reporting() {
  const [categories, setCategories] = useState<Category[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listCategories()
      .then(setCategories)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  return (
    <section>
      <h1 className="mb-6 text-2xl font-semibold tracking-tight text-slate-900">
        Reporting
      </h1>

      <ErrorText>{error}</ErrorText>

      {categories === null && !error ? (
        <CardSkeletons count={4} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {(categories ?? []).map((c) => (
            <Link
              key={c.category}
              to={`/reporting/${encodeURIComponent(c.category)}`}
              className="group flex flex-col justify-between rounded-lg border border-slate-200 bg-white p-5 transition-all hover:border-slate-400 hover:shadow-sm"
            >
              <div className="flex items-start justify-between">
                <h2 className="text-lg font-semibold tracking-tight text-slate-900">
                  {c.category}
                </h2>
                <span className="rounded-md bg-slate-100 px-2 py-0.5 font-mono text-xs font-medium text-slate-500">
                  {c.active_count}
                </span>
              </div>

              <div className="mt-6 flex items-center gap-2 border-t border-slate-100 pt-3 text-xs">
                {c.last_run ? (
                  <>
                    <span className="h-1.5 w-1.5 rounded-full bg-slate-300" />
                    <span className="text-slate-400">
                      Last run {formatDate(c.last_run.reference_date)}
                    </span>
                    <span className="ml-auto">
                      <RunStatusBadge status={c.last_run.status} />
                    </span>
                  </>
                ) : (
                  <span className="text-slate-300">No activity yet</span>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </section>
  )
}
