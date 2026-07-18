import { useEffect, useState } from 'react'
import { listRegulators, type Regulator } from '../api/snapshots'
import { Card, ErrorText, RowLink, TableSkeleton } from '../components/ui'

export default function Regulators() {
  const [regulators, setRegulators] = useState<Regulator[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listRegulators()
      .then(setRegulators)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  return (
    <section>
      <h1 className="mb-6 text-2xl font-semibold tracking-tight text-slate-900">
        Taxonomies
      </h1>

      <ErrorText>{error}</ErrorText>

      {regulators === null && !error ? (
        <TableSkeleton rows={3} />
      ) : (
        <Card className="divide-y divide-slate-100">
          {(regulators ?? []).map((r) => (
            <RowLink
              key={r.id}
              to={`/releases/regulators/${r.id}`}
              title={r.name}
              subtitle={r.code}
            />
          ))}
        </Card>
      )}
    </section>
  )
}
