import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createEntity, listEntities, type Entity } from '../api/workflows'
import EntityForm from '../components/EntityForm'
import {
  Card,
  EmptyState,
  ErrorText,
  Loading,
  PageHeader,
  primaryBtn,
} from '../components/ui'

export default function ReferenceData() {
  const navigate = useNavigate()
  const [entities, setEntities] = useState<Entity[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showNew, setShowNew] = useState(false)

  const refresh = useCallback(() => {
    listEntities()
      .then(setEntities)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  return (
    <section>
      <PageHeader
        title="Reference Data"
        actions={
          <button
            type="button"
            className={primaryBtn}
            onClick={() => setShowNew((v) => !v)}
          >
            {showNew ? 'Cancel' : '+ New entity'}
          </button>
        }
      />

      {showNew && (
        <Card className="mb-6 p-5">
          <h2 className="mb-4 text-sm font-semibold text-slate-900">New entity</h2>
          <EntityForm
            submitLabel="Create entity"
            onCancel={() => setShowNew(false)}
            onSubmit={async (body) => {
              const created = await createEntity(body)
              setShowNew(false)
              navigate(`/reference/entities/${created.id}`)
            }}
          />
        </Card>
      )}

      <ErrorText>{error}</ErrorText>

      {entities === null && !error ? (
        <Loading />
      ) : entities && entities.length === 0 ? (
        <EmptyState>
          No entities yet. Use <span className="font-medium">+ New entity</span>{' '}
          to add one.
        </EmptyState>
      ) : (
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs font-medium text-slate-500">
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">LEI</th>
                <th className="px-4 py-3">Country</th>
                <th className="px-4 py-3">Scope</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {(entities ?? []).map((e) => (
                <tr
                  key={e.id}
                  onClick={() => navigate(`/reference/entities/${e.id}`)}
                  className="cursor-pointer border-b border-slate-100 transition-colors last:border-0 hover:bg-slate-50"
                >
                  <td className="px-4 py-3 font-medium text-slate-900">
                    {e.name}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-500">
                    {e.lei}
                  </td>
                  <td className="px-4 py-3 text-slate-600">{e.country}</td>
                  <td className="px-4 py-3 text-slate-600">{e.default_scope}</td>
                  <td className="px-4 py-3 text-right text-slate-300">→</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </section>
  )
}
