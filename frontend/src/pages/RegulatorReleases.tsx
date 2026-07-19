import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  getRegulator,
  listRegulatorReleases,
  type Regulator,
  type Snapshot,
} from '../api/snapshots'
import StatusBadge from '../components/StatusBadge'
import {
  Card,
  EmptyState,
  ErrorText,
  PageHeader,
  TableSkeleton,
  primaryBtn,
} from '../components/ui'
import { formatDate } from '../lib/format'

export default function RegulatorReleases() {
  const { regulatorId } = useParams()
  const id = Number(regulatorId)
  const navigate = useNavigate()
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
        crumbs={[
          { label: 'Taxonomies', to: '/releases' },
          { label: regulator?.name ?? '' },
        ]}
        title={regulator?.name ?? 'Releases'}
        actions={
          <Link to={`/releases/regulators/${id}/new`} className={primaryBtn}>
            New release
          </Link>
        }
      />

      <ErrorText>{error}</ErrorText>

      {releases === null && !error ? (
        <TableSkeleton rows={4} />
      ) : releases && releases.length === 0 ? (
        <EmptyState>
          No taxonomies yet. Create one from its three EBA files.
        </EmptyState>
      ) : (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-[11px] font-medium uppercase tracking-wide text-slate-400">
                <th className="px-4 py-3 font-medium">Taxonomy</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Added</th>
              </tr>
            </thead>
            <tbody>
              {(releases ?? []).map((r) => (
                <tr
                  key={r.id}
                  className="cursor-pointer border-b border-slate-100 last:border-0 hover:bg-slate-50"
                  onClick={() => navigate(`/releases/${r.id}`)}
                >
                  <td className="px-4 py-3">
                    <span className="font-medium text-slate-900 hover:underline">
                      {r.display_name}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={r.status} />
                  </td>
                  <td className="px-4 py-3 text-xs tabular-nums text-slate-400">
                    {formatDate(r.uploaded_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </section>
  )
}
