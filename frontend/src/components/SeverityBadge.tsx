import type { Severity } from '../api/workflows'

const STYLES: Record<Severity, string> = {
  error: 'bg-red-100 text-red-800 ring-red-600/20',
  warning: 'bg-amber-100 text-amber-800 ring-amber-600/20',
  info: 'bg-sky-100 text-sky-800 ring-sky-600/20',
}

export default function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${STYLES[severity]}`}
    >
      {severity}
    </span>
  )
}
