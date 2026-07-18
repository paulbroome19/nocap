import type { RunStatus } from '../api/workflows'

// Humanised run-status display vocabulary (display-layer only; the backend
// statuses are unchanged). Successful / Failed / Running / Validating / Draft.
export const RUN_STATUS_LABEL: Record<RunStatus, string> = {
  created: 'Draft',
  files_attached: 'Draft',
  running: 'Running',
  formula_validation_running: 'Validating',
  generated: 'Successful',
  failed_validation: 'Failed',
  failed: 'Failed',
}

export function runStatusLabel(status: RunStatus): string {
  return RUN_STATUS_LABEL[status] ?? status
}
