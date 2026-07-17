import type { SnapshotStatus } from '../api/snapshots'

const STYLES: Record<SnapshotStatus, string> = {
  ingesting: 'bg-amber-100 text-amber-800 ring-amber-600/20',
  ready: 'bg-emerald-100 text-emerald-800 ring-emerald-600/20',
  failed: 'bg-red-100 text-red-800 ring-red-600/20',
}

export default function StatusBadge({ status }: { status: SnapshotStatus }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${STYLES[status]}`}
    >
      {status === 'ingesting' && (
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-500" />
      )}
      {status}
    </span>
  )
}
