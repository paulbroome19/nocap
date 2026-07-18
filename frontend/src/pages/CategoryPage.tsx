import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { listCategorySuites, type SuiteSummary } from '../api/workflows'
import {
  Card,
  EmptyState,
  ErrorText,
  PageHeader,
  RowLink,
  TableSkeleton,
} from '../components/ui'

export default function CategoryPage() {
  const { regulatorCode = '', category = '' } = useParams()
  const name = decodeURIComponent(category)
  const [suites, setSuites] = useState<SuiteSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setSuites(null)
    listCategorySuites(name)
      .then(setSuites)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [name])

  const sorted = [...(suites ?? [])].sort((a, b) => a.name.localeCompare(b.name))

  return (
    <section>
      <PageHeader
        title={name}
        crumbs={[
          { label: 'Reporting', to: '/reporting' },
          { label: regulatorCode, to: `/reporting/${regulatorCode}` },
          { label: name },
        ]}
      />

      <ErrorText>{error}</ErrorText>

      {suites === null && !error ? (
        <TableSkeleton rows={4} />
      ) : suites && suites.length === 0 ? (
        <EmptyState>No active suites in this category.</EmptyState>
      ) : (
        <Card className="divide-y divide-slate-100">
          {sorted.map((s) => (
            <RowLink
              key={s.id}
              to={`/reporting/suites/${s.id}`}
              title={s.name}
              subtitle={s.module_code}
            />
          ))}
        </Card>
      )}
    </section>
  )
}
