import type { RunStatus } from '../api/workflows'

const STYLES: Record<RunStatus, string> = {
  created: 'bg-slate-100 text-slate-700 ring-slate-600/20',
  files_attached: 'bg-sky-100 text-sky-800 ring-sky-600/20',
  running: 'bg-amber-100 text-amber-800 ring-amber-600/20',
  formula_validation_running: 'bg-amber-100 text-amber-800 ring-amber-600/20',
  generated: 'bg-emerald-100 text-emerald-800 ring-emerald-600/20',
  failed_validation: 'bg-red-100 text-red-800 ring-red-600/20',
  failed: 'bg-red-100 text-red-800 ring-red-600/20',
}

const LABELS: Record<RunStatus, string> = {
  created: 'created',
  files_attached: 'files attached',
  running: 'running',
  formula_validation_running: 'formula validation',
  generated: 'generated',
  failed_validation: 'failed validation',
  failed: 'failed',
}

const IN_PROGRESS: RunStatus[] = ['running', 'formula_validation_running']

export default function RunStatusBadge({ status }: { status: RunStatus }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${STYLES[status]}`}
    >
      {IN_PROGRESS.includes(status) && (
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-amber-500" />
      )}
      {LABELS[status]}
    </span>
  )
}
