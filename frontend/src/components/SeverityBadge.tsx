import type { Severity } from '../api/workflows'

// Red only for error (a failure); warning/info neutral (red/gold law).
const STYLE: Record<Severity, string> = {
  error: 'text-red',
  warning: 'text-data',
  info: 'text-muted',
}
const LABEL: Record<Severity, string> = {
  error: 'Error',
  warning: 'Warning',
  info: 'Info',
}

export default function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className={`text-[12px] font-medium ${STYLE[severity]}`}>
      {LABEL[severity]}
    </span>
  )
}
