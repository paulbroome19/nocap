import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { listRegulators, type Regulator } from '../api/snapshots'
import { listCategorySuites, type SuiteSummary } from '../api/workflows'
import {
  Block,
  EmptyState,
  ErrorText,
  PageHeader,
  RowLink,
  SectionLabel,
  TableSkeleton,
} from '../components/ui'
import { runStatusLabel } from '../lib/status'
import { formatDate } from '../lib/format'

export default function CategoryPage() {
  const { regulatorCode = '', category = '' } = useParams()
  const name = decodeURIComponent(category)
  const [regulator, setRegulator] = useState<Regulator | null>(null)
  const [suites, setSuites] = useState<SuiteSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setSuites(null)
    listRegulators()
      .then((rs) => setRegulator(rs.find((r) => r.code === regulatorCode) ?? null))
      .catch(() => {})
    listCategorySuites(name)
      .then(setSuites)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [name, regulatorCode])

  const sorted = [...(suites ?? [])].sort((a, b) => a.name.localeCompare(b.name))

  return (
    <section>
      <PageHeader
        title={name}
        crumbs={[
          { label: 'Reporting', to: '/reporting' },
          { label: regulator?.name ?? regulatorCode, to: `/reporting/${regulatorCode}` },
          { label: name },
        ]}
      />
      <ErrorText>{error}</ErrorText>

      <SectionLabel>Suite</SectionLabel>
      {suites === null && !error ? (
        <TableSkeleton rows={4} />
      ) : suites && suites.length === 0 ? (
        <EmptyState>No active suites in this category.</EmptyState>
      ) : (
        <Block>
          {sorted.map((s) => (
            <RowLink
              key={s.id}
              to={`/reporting/suites/${s.id}`}
              title={s.name}
              right={
                s.last_run ? (
                  <span className="text-[12px] text-muted">
                    {runStatusLabel(s.last_run.status)}
                    <span className="mx-1.5 text-faint">·</span>
                    <span className="font-mono">
                      {formatDate(s.last_run.reference_date)}
                    </span>
                  </span>
                ) : (
                  <span className="text-[12px] text-muted">No submissions</span>
                )
              }
            />
          ))}
        </Block>
      )}
    </section>
  )
}
