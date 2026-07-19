import { useCallback, useEffect, useState } from 'react'
import { Outlet, useParams } from 'react-router-dom'
import { getSnapshot, type Snapshot } from '../../api/snapshots'
import {
  getConfig,
  getEntity,
  getRunDetail,
  getRunFacts,
  runHistory,
  type Entity,
  type FactRow,
  type Run,
  type RunDetail as RunDetailT,
  type WorkflowConfig,
} from '../../api/workflows'
import { ErrorText, Skeleton } from '../../components/ui'
import { usePrimaryRegulator } from '../../lib/useRegulator'
import { instanceSiblings, type RunCtx } from './context'

export default function RunLayout() {
  const { runId } = useParams()
  const id = Number(runId)
  const regulatorCode = usePrimaryRegulator()?.code ?? ''
  const [detail, setDetail] = useState<RunDetailT | null>(null)
  const [config, setConfig] = useState<WorkflowConfig | null>(null)
  const [entity, setEntity] = useState<Entity | null>(null)
  const [release, setRelease] = useState<Snapshot | null>(null)
  const [entityMissing, setEntityMissing] = useState(false)
  const [releaseMissing, setReleaseMissing] = useState(false)
  const [facts, setFacts] = useState<FactRow[] | null>(null)
  const [siblings, setSiblings] = useState<Run[]>([])
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(() => {
    getRunDetail(id)
      .then((d) => {
        setDetail(d)
        getConfig(d.run.workflow_id).then(setConfig)
        // The entity/release may have been deleted since this run executed. The
        // run renders its frozen values regardless; we track the absence so the
        // detail can say so plainly instead of silently degrading.
        if (d.run.entity_id) {
          getEntity(d.run.entity_id)
            .then((e) => {
              setEntity(e)
              setEntityMissing(false)
            })
            .catch(() => setEntityMissing(true))
        }
        getSnapshot(d.run.snapshot_id)
          .then((r) => {
            setRelease(r)
            setReleaseMissing(false)
          })
          .catch(() => setReleaseMissing(true))
        runHistory(d.run.workflow_id)
          .then((h) => setSiblings(instanceSiblings(d.run, h)))
          .catch(() => setSiblings([]))
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
    getRunFacts(id).then(setFacts).catch(() => setFacts([]))
  }, [id])

  useEffect(() => {
    setDetail(null)
    reload()
  }, [reload])

  const inProgress =
    detail?.run.status === 'running' ||
    detail?.run.status === 'formula_validation_running'
  useEffect(() => {
    if (!inProgress) return
    const t = setInterval(reload, 1500)
    return () => clearInterval(t)
  }, [inProgress, reload])

  if (error) return <ErrorText>{error}</ErrorText>
  if (!detail)
    return (
      <div className="space-y-4">
        <Skeleton className="h-6 w-64" />
        <Skeleton className="h-24" />
        <Skeleton className="h-40" />
      </div>
    )

  const ctx: RunCtx = {
    id, detail, config, entity, release, entityMissing, releaseMissing,
    facts, siblings, regulatorCode, reload,
  }
  return <Outlet context={ctx} />
}
