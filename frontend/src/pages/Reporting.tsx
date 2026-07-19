import { useEffect, useState } from 'react'
import { listRegulators, type Regulator } from '../api/snapshots'
import {
  Block,
  EmptyState,
  ErrorText,
  PageHeader,
  RowLink,
  SectionLabel,
  TableSkeleton,
} from '../components/ui'

export default function Reporting() {
  const [regulators, setRegulators] = useState<Regulator[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listRegulators()
      .then(setRegulators)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  return (
    <section>
      <PageHeader title="Reporting" />
      <ErrorText>{error}</ErrorText>

      <SectionLabel>Regulator</SectionLabel>
      {regulators === null && !error ? (
        <TableSkeleton rows={1} />
      ) : regulators && regulators.length === 0 ? (
        <EmptyState>No regulators are set up yet.</EmptyState>
      ) : (
        <Block>
          {(regulators ?? []).map((r) => (
            <RowLink
              key={r.id}
              to={`/reporting/${r.code}`}
              title={r.name}
              subtitle={r.code}
            />
          ))}
        </Block>
      )}
    </section>
  )
}
