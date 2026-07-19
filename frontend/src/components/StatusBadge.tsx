import type { SnapshotStatus } from '../api/snapshots'

// Business-language release status; red only for a failure, neutral otherwise.
// (Transactional creation means the list only ever shows Ready / Files missing.)
const LABEL: Record<SnapshotStatus, string> = {
  ingesting: 'Preparing',
  ready: 'Ready',
  failed: 'Failed',
  artifacts_missing: 'Files missing',
}
const STYLE: Record<SnapshotStatus, string> = {
  ingesting: 'text-muted',
  ready: 'text-data',
  failed: 'text-red',
  artifacts_missing: 'text-muted',
}

export default function StatusBadge({ status }: { status: SnapshotStatus }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[13px] font-medium">
      {status === 'ingesting' && (
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted" />
      )}
      <span className={STYLE[status]}>{LABEL[status]}</span>
    </span>
  )
}
