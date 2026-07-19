import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  getRegulator,
  listRegulatorReleases,
  type Regulator,
  type Snapshot,
} from '../api/snapshots'
import StatusBadge from '../components/StatusBadge'
import {
  Block,
  EmptyState,
  ErrorText,
  PageHeader,
  RowLink,
  SectionLabel,
  TableSkeleton,
  primaryBtn,
} from '../components/ui'
import { formatDate } from '../lib/format'

export default function RegulatorReleases() {
  const { regulatorId } = useParams()
  const id = Number(regulatorId)
  const [regulator, setRegulator] = useState<Regulator | null>(null)
  const [releases, setReleases] = useState<Snapshot[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    listRegulatorReleases(id)
      .then(setReleases)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [id])

  useEffect(() => {
    getRegulator(id).then(setRegulator).catch(() => {})
    load()
  }, [id, load])

  return (
    <section>
      <PageHeader
        crumbs={[{ label: 'Taxonomies', to: '/releases' }, { label: regulator?.name ?? '' }]}
        title={regulator?.name ?? 'Releases'}
        actions={
          <Link to={`/releases/regulators/${id}/new`} className={primaryBtn}>
            New release
          </Link>
        }
      />
      <ErrorText>{error}</ErrorText>

      <SectionLabel>Release</SectionLabel>
      {releases === null && !error ? (
        <TableSkeleton rows={3} />
      ) : releases && releases.length === 0 ? (
        <EmptyState>
          No taxonomy releases yet. Add one from the regulator&rsquo;s three
          published files.
        </EmptyState>
      ) : (
        <Block>
          {(releases ?? []).map((r) => (
            <RowLink
              key={r.id}
              to={`/releases/${r.id}`}
              title={r.display_name}
              right={
                <span className="flex items-center gap-4">
                  <StatusBadge status={r.status} />
                  <span className="font-mono text-[12px] text-muted">
                    {formatDate(r.uploaded_at)}
                  </span>
                </span>
              }
            />
          ))}
        </Block>
      )}
    </section>
  )
}
