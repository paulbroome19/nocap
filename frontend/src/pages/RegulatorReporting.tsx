import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { listRegulators, type Regulator } from '../api/snapshots'
import { listCategories, type Category } from '../api/workflows'
import { Card, ErrorText, PageHeader, RowLink, TableSkeleton } from '../components/ui'

export default function RegulatorReporting() {
  const { regulatorCode = '' } = useParams()
  const [regulator, setRegulator] = useState<Regulator | null>(null)
  const [categories, setCategories] = useState<Category[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listRegulators()
      .then((rs) => setRegulator(rs.find((r) => r.code === regulatorCode) ?? null))
      .catch(() => {})
    listCategories()
      .then(setCategories)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [regulatorCode])

  return (
    <section>
      <PageHeader
        crumbs={[{ label: 'Reporting', to: '/reporting' }, { label: regulatorCode }]}
        title={regulator?.name ?? regulatorCode}
      />

      <ErrorText>{error}</ErrorText>

      {categories === null && !error ? (
        <TableSkeleton rows={4} />
      ) : (
        <Card className="divide-y divide-slate-100">
          {(categories ?? []).map((c) => (
            <RowLink
              key={c.category}
              to={`/reporting/${regulatorCode}/${encodeURIComponent(c.category)}`}
              title={c.category}
            />
          ))}
        </Card>
      )}
    </section>
  )
}
