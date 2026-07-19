import { useOutletContext } from 'react-router-dom'
import type { Snapshot } from '../../api/snapshots'
import type {
  Entity,
  FactRow,
  Run,
  RunDetail as RunDetailT,
  WorkflowConfig,
} from '../../api/workflows'
import type { Crumb } from '../../components/ui'
import { formatDate } from '../../lib/format'

export interface RunCtx {
  id: number
  detail: RunDetailT
  config: WorkflowConfig | null
  entity: Entity | null
  release: Snapshot | null
  // The live entity/release referenced by this run no longer exists (deleted).
  // The run still renders its frozen values; a re-execution asks for a current one.
  entityMissing: boolean
  releaseMissing: boolean
  facts: FactRow[] | null
  siblings: Run[] // executions of the same instance, newest first
  regulatorCode: string // the publisher level in the reporting breadcrumb
  reload: () => void
}

export function useRun(): RunCtx {
  return useOutletContext<RunCtx>()
}

/** The runs sharing a run's submission-instance identity, newest first. */
export function instanceSiblings(run: Run, history: Run[]): Run[] {
  const same = (r: Run) =>
    r.entity_id === run.entity_id &&
    r.reference_date === run.reference_date &&
    r.snapshot_key === run.snapshot_key &&
    r.adjusted_key === run.adjusted_key &&
    r.version_key === run.version_key
  return history.filter(same).sort((a, b) => b.id - a.id)
}

/**
 * Breadcrumb trail down to the run instance (never a run number). `leaf` adds a
 * final non-link crumb for a sub-page.
 */
export function runCrumbs(ctx: RunCtx, leaf?: string): Crumb[] {
  const { detail, config, id, regulatorCode } = ctx
  const category = config?.category ?? 'Reporting'
  const instanceLabel = formatDate(detail.run.reference_date)
  const crumbs: Crumb[] = [
    { label: 'Reporting', to: '/reporting' },
    ...(regulatorCode
      ? [{ label: regulatorCode, to: `/reporting/${regulatorCode}` }]
      : []),
    {
      label: category,
      to: regulatorCode
        ? `/reporting/${regulatorCode}/${encodeURIComponent(category)}`
        : '/reporting',
    },
    {
      label: config?.name ?? 'Suite',
      to: `/reporting/suites/${detail.run.workflow_id}`,
    },
    leaf
      ? { label: instanceLabel, to: `/reporting/runs/${id}` }
      : { label: instanceLabel },
  ]
  if (leaf) crumbs.push({ label: leaf })
  return crumbs
}
