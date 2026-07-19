import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { createEntity, listEntities, type Entity } from '../api/workflows'
import EntityForm from '../components/EntityForm'
import {
  Block,
  EmptyState,
  ErrorText,
  PageHeader,
  SectionLabel,
  TableSkeleton,
  primaryBtn,
} from '../components/ui'

export default function EntitySetup() {
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
        crumbs={[{ label: 'Reference Data', to: '/reference' }, { label: 'Entity Setup' }]}
        title="Entity Setup"
        actions={
          !showNew && (
            <button type="button" className={primaryBtn} onClick={() => setShowNew(true)}>
              New entity
            </button>
          )
        }
      />

      {showNew && (
        <div className="mb-10">
          <SectionLabel>New entity</SectionLabel>
          <Block className="p-6">
            <EntityForm
              submitLabel="Create entity"
              onCancel={() => setShowNew(false)}
              onSubmit={async (body) => {
                const created = await createEntity(body)
                setShowNew(false)
                navigate(`/reference/entities/${created.id}`)
              }}
            />
          </Block>
        </div>
      )}

      <ErrorText>{error}</ErrorText>

      <SectionLabel>Entity</SectionLabel>
      {entities === null && !error ? (
        <TableSkeleton />
      ) : entities && entities.length === 0 ? (
        <EmptyState>No entities yet. Use “New entity” to add one.</EmptyState>
      ) : (
        <Block>
          {(entities ?? []).map((e) => (
            <Link
              key={e.id}
              to={`/reference/entities/${e.id}`}
              className="flex items-center justify-between gap-4 border-t border-divider px-6 py-[22px] transition-colors first:border-t-0 hover:bg-hover"
            >
              <div className="min-w-0">
                <div className="truncate text-[15px] font-semibold text-ink">{e.name}</div>
                <div className="mt-1 font-mono text-[12px] text-muted">
                  {e.lei}
                  <span className="mx-1.5 text-faint">·</span>
                  {e.country}
                  <span className="mx-1.5 text-faint">·</span>
                  {e.default_scope}
                </div>
              </div>
              <span className="text-[18px] leading-none text-faint">→</span>
            </Link>
          ))}
        </Block>
      )}
    </section>
  )
}
