import type { RunStatus } from '../api/workflows'
import { RUN_STATUS_LABEL as LABELS } from '../lib/status'

// Business-language status; red only for a failure, a pulsing muted dot while in
// progress, neutral otherwise (red/gold law — no decorative colour).
const IN_PROGRESS: RunStatus[] = ['running', 'formula_validation_running']
const FAILED: RunStatus[] = ['failed', 'failed_validation']

export default function RunStatusBadge({ status }: { status: RunStatus }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[13px] font-medium">
      {IN_PROGRESS.includes(status) && (
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted" />
      )}
      <span className={FAILED.includes(status) ? 'text-red' : 'text-data'}>
        {LABELS[status]}
      </span>
    </span>
  )
}
