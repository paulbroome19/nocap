import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getEntity, updateEntity, type Entity } from '../api/workflows'
import EntityForm from '../components/EntityForm'
import {
  Card,
  ErrorText,
  Loading,
  PageHeader,
  secondaryBtn,
} from '../components/ui'

export default function EntityDetail() {
  const { entityId } = useParams()
  const id = Number(entityId)

  const [entity, setEntity] = useState<Entity | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)

  const loadEntity = useCallback(() => {
    getEntity(id)
      .then(setEntity)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [id])

  useEffect(() => {
    loadEntity()
  }, [loadEntity])

  if (error) return <ErrorText>{error}</ErrorText>
  if (!entity) return <Loading />

  const meta: [string, string][] = [
    ['LEI', entity.lei],
    ['Country', entity.country],
    ['Default scope', entity.default_scope],
  ]

  return (
    <section>
      <PageHeader
        crumbs={[
          { label: 'Reference Data', to: '/reference' },
          { label: 'Entity Setup', to: '/reference/entities' },
          { label: entity.name },
        ]}
        title={entity.name}
        actions={
          !editing && (
            <button
              type="button"
              className={secondaryBtn}
              onClick={() => setEditing(true)}
            >
              Edit
            </button>
          )
        }
      />

      {editing ? (
        <Card className="p-5">
          <h2 className="mb-4 text-sm font-semibold text-slate-900">
            Edit entity
          </h2>
          <EntityForm
            initial={entity}
            submitLabel="Save changes"
            onCancel={() => setEditing(false)}
            onSubmit={async (body) => {
              const updated = await updateEntity(id, body)
              setEntity(updated)
              setEditing(false)
            }}
          />
        </Card>
      ) : (
        <Card className="p-5">
          <dl className="grid grid-cols-3 gap-6 text-sm">
            {meta.map(([k, v]) => (
              <div key={k}>
                <dt className="text-xs text-slate-400">{k}</dt>
                <dd className="mt-0.5 font-mono text-slate-800">{v}</dd>
              </div>
            ))}
          </dl>
        </Card>
      )}
    </section>
  )
}
