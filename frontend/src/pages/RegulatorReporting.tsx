import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { listRegulators, type Regulator } from '../api/snapshots'
import { listCategories, type Category } from '../api/workflows'
import {
  Block,
  EmptyState,
  ErrorText,
  PageHeader,
  RowLink,
  SectionLabel,
  TableSkeleton,
} from '../components/ui'
import { byCategoryOrder } from '../lib/categories'

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

  const ordered = byCategoryOrder(categories ?? [], (c) => c.category)

  return (
    <section>
      <PageHeader
        crumbs={[{ label: 'Reporting', to: '/reporting' }, { label: regulator?.name ?? regulatorCode }]}
        title={regulator?.name ?? regulatorCode}
      />
      <ErrorText>{error}</ErrorText>

      <SectionLabel>Category</SectionLabel>
      {categories === null && !error ? (
        <TableSkeleton rows={4} />
      ) : categories && categories.length === 0 ? (
        <EmptyState>No reporting categories are active yet.</EmptyState>
      ) : (
        <Block>
          {ordered.map((c) => (
            <RowLink
              key={c.category}
              to={`/reporting/${regulatorCode}/${encodeURIComponent(c.category)}`}
              title={c.category}
            />
          ))}
        </Block>
      )}
    </section>
  )
}
