import { useEffect, useState } from 'react'
import { listRegulators, type Regulator } from '../api/snapshots'
import {
  Block,
  ErrorText,
  PageHeader,
  RowLink,
  SectionLabel,
  TableSkeleton,
} from '../components/ui'

export default function SettingsReporting() {
  const [regulators, setRegulators] = useState<Regulator[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listRegulators()
      .then(setRegulators)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  return (
    <section>
      <PageHeader
        crumbs={[{ label: 'Settings', to: '/settings' }, { label: 'Reporting' }]}
        title="Reporting"
      />
      <ErrorText>{error}</ErrorText>

      <SectionLabel>Regulator</SectionLabel>
      {regulators === null && !error ? (
        <TableSkeleton rows={2} />
      ) : (
        <Block>
          {(regulators ?? []).map((r) => (
            <RowLink
              key={r.id}
              to={`/settings/reporting/${r.code}`}
              title={r.name}
              subtitle={r.code}
            />
          ))}
        </Block>
      )}
    </section>
  )
}
