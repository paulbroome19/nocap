import { useEffect, useState } from 'react'
import { listCategories, type Category } from '../api/workflows'
import { Card, ErrorText, RowLink, TableSkeleton } from '../components/ui'

export default function Reporting() {
  const [categories, setCategories] = useState<Category[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listCategories()
      .then(setCategories)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  // Server returns categories in curated order (Capital, Liquidity, Financial,
  // Last Mile Reporting) — preserve it, do not re-sort alphabetically.
  const ordered = categories ?? []

  return (
    <section>
      <h1 className="mb-6 text-2xl font-semibold tracking-tight text-slate-900">
        Reporting
      </h1>

      <ErrorText>{error}</ErrorText>

      {categories === null && !error ? (
        <TableSkeleton rows={4} />
      ) : (
        <Card className="divide-y divide-slate-100">
          {ordered.map((c) => (
            <RowLink
              key={c.category}
              to={`/reporting/${encodeURIComponent(c.category)}`}
              title={c.category}
            />
          ))}
        </Card>
      )}
    </section>
  )
}
