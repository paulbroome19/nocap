import { useEffect, useState } from 'react'
import {
  listRegulatorReleases,
  listRegulators,
  type Regulator,
} from '../api/snapshots'
import {
  listConfigs,
  listEntities,
  type Entity,
  type WorkflowConfig,
} from '../api/workflows'
import { Select } from './ui'

export interface EwcTarget {
  entityId: number
  workflowId: number
  snapshotId: number // the regulator's current ready release, for template lookup
}

/**
 * The shared Entity → Regulator → Suite dropdown row for the per-(entity,
 * workflow) reference screens. The regulator's current ready release is
 * resolved automatically for template lookup — it is not a user choice. Calls
 * `onChange` with the full target once all three are chosen (else null); calls
 * `onNoRelease` when the chosen regulator has no ready release.
 */
export default function EwcSelectors({
  onChange,
  onNoRelease,
}: {
  onChange: (t: EwcTarget | null) => void
  onNoRelease?: (noRelease: boolean) => void
}) {
  const [entities, setEntities] = useState<Entity[]>([])
  const [regulators, setRegulators] = useState<Regulator[]>([])
  const [suites, setSuites] = useState<WorkflowConfig[]>([])
  const [entityId, setEntityId] = useState<number | ''>('')
  const [regulatorId, setRegulatorId] = useState<number | ''>('')
  const [workflowId, setWorkflowId] = useState<number | ''>('')
  const [snapshotId, setSnapshotId] = useState<number | null>(null)

  useEffect(() => {
    listEntities().then(setEntities).catch(() => {})
    listConfigs().then(setSuites).catch(() => {})
    listRegulators()
      .then((rs) => {
        setRegulators(rs)
        if (rs.length === 1) setRegulatorId(rs[0].id) // preselect the sole publisher
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (regulatorId === '') {
      setSnapshotId(null)
      return
    }
    listRegulatorReleases(regulatorId)
      .then((rs) => {
        const ready = rs.find((r) => r.status === 'ready')
        setSnapshotId(ready ? ready.id : null)
        onNoRelease?.(!ready)
      })
      .catch(() => setSnapshotId(null))
  }, [regulatorId, onNoRelease])

  useEffect(() => {
    if (entityId !== '' && workflowId !== '' && snapshotId !== null) {
      onChange({ entityId, workflowId, snapshotId })
    } else {
      onChange(null)
    }
  }, [entityId, workflowId, snapshotId, onChange])

  return (
    <div className="grid gap-4 sm:grid-cols-3">
      <label className="flex flex-col gap-1">
        <span className="text-xs font-medium text-slate-600">Entity</span>
        <Select
          value={entityId}
          onChange={(v) => setEntityId(v === '' ? '' : Number(v))}
        >
          <option value="">Select…</option>
          {entities.map((e) => (
            <option key={e.id} value={e.id}>
              {e.name} · {e.lei}
            </option>
          ))}
        </Select>
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs font-medium text-slate-600">Regulator</span>
        <Select
          value={regulatorId}
          onChange={(v) => setRegulatorId(v === '' ? '' : Number(v))}
        >
          <option value="">Select…</option>
          {regulators.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </Select>
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-xs font-medium text-slate-600">Reporting suite</span>
        <Select
          value={workflowId}
          onChange={(v) => setWorkflowId(v === '' ? '' : Number(v))}
        >
          <option value="">Select…</option>
          {suites.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </Select>
      </label>
    </div>
  )
}
