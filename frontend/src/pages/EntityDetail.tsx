import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  deleteEntity,
  getEntity,
  updateEntity,
  type Entity,
} from '../api/workflows'
import EntityForm from '../components/EntityForm'
import {
  Block,
  ErrorText,
  Loading,
  PageHeader,
  SectionLabel,
  dangerText,
  secondaryBtn,
} from '../components/ui'

export default function EntityDetail() {
  const { entityId } = useParams()
  const id = Number(entityId)
  const navigate = useNavigate()

  const [entity, setEntity] = useState<Entity | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)

  async function handleDelete() {
    if (!entity) return
    const message =
      `Delete ${entity.name}?\n\n` +
      'This removes the entity and its per-suite configuration. Submissions ' +
      'already produced for it are unaffected — they keep the values they used. ' +
      'This cannot be undone.'
    if (!window.confirm(message)) return
    setBusy(true)
    try {
      await deleteEntity(id)
      navigate('/reference/entities')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setBusy(false)
    }
  }

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
            <div className="flex items-center gap-4">
              <button type="button" className={secondaryBtn} onClick={() => setEditing(true)}>
                Edit
              </button>
              <button
                type="button"
                disabled={busy}
                className={`${dangerText} disabled:hover:text-sub`}
                onClick={() => void handleDelete()}
              >
                {busy ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          )
        }
      />

      {editing ? (
        <>
          <SectionLabel>Edit entity</SectionLabel>
          <Block className="p-6">
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
          </Block>
        </>
      ) : (
        <>
          <SectionLabel>Details</SectionLabel>
          <Block className="p-6">
            <dl className="grid grid-cols-3 gap-8">
              {meta.map(([k, v]) => (
                <div key={k}>
                  <dt className="text-[11px] font-medium uppercase tracking-[0.08em] text-muted">
                    {k}
                  </dt>
                  <dd className="mt-1 font-mono text-[14px] text-data">{v}</dd>
                </div>
              ))}
            </dl>
          </Block>
        </>
      )}
    </section>
  )
}
