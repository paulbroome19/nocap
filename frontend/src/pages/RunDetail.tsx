import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  getRunDetail,
  runFileDownloadUrl,
  type RunDetail as RunDetailT,
} from '../api/workflows'
import RunStatusBadge from '../components/RunStatusBadge'
import SeverityBadge from '../components/SeverityBadge'
import type { Finding } from '../api/workflows'

function findingLocation(f: Finding): string {
  const parts: string[] = []
  if (f.file) {
    let loc = f.file
    if (f.sheet) loc += ` · ${f.sheet}`
    if (f.row != null) loc += ` · row ${f.row}`
    parts.push(loc)
  }
  const cell = [
    f.template_code,
    f.row_code ? `r${f.row_code}` : null,
    f.column_code ? `c${f.column_code}` : null,
  ]
    .filter(Boolean)
    .join(' ')
  if (cell) parts.push(cell)
  return parts.join('  ·  ') || '—'
}

const ROLE_LABELS: Record<string, string> = {
  fact_input: 'Fact input',
  indicators_params: 'Indicators / parameters',
  package_output: 'Package (output)',
  validation_report: 'Validation report',
}

export default function RunDetail() {
  const { runId } = useParams()
  const id = Number(runId)
  const [detail, setDetail] = useState<RunDetailT | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    getRunDetail(id)
      .then(setDetail)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  // Poll while running.
  useEffect(() => {
    if (detail?.run.status !== 'running') return
    const t = setInterval(load, 1500)
    return () => clearInterval(t)
  }, [detail?.run.status, load])

  if (error) return <p className="text-sm text-red-600">{error}</p>
  if (!detail) return <p className="text-sm text-slate-400">Loading…</p>

  const { run, files, findings } = detail
  const outputs = files.filter((f) => f.role === 'package_output')
  const reports = files.filter((f) => f.role === 'validation_report')
  const inputs = files.filter(
    (f) => f.role === 'fact_input' || f.role === 'indicators_params',
  )
  const notSubmittable = run.status === 'failed_validation'
  const errorCount = findings.filter((f) => f.severity === 'error').length

  const meta: [string, string][] = [
    ['Reference date', run.reference_date],
    ['Entity', `${run.entity_lei}.${run.entity_scope}`],
    ['Country', run.country],
    ['Release', String(run.release_id)],
  ]

  return (
    <section>
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Run #{run.id}</h1>
        <RunStatusBadge status={run.status} />
      </div>

      <dl className="mt-4 grid max-w-2xl grid-cols-2 gap-x-8 gap-y-2 text-sm sm:grid-cols-4">
        {meta.map(([k, v]) => (
          <div key={k}>
            <dt className="text-xs text-slate-400">{k}</dt>
            <dd className="text-slate-800">{v}</dd>
          </div>
        ))}
      </dl>

      {run.status === 'failed' && (
        <div className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4">
          <p className="text-sm font-medium text-red-800">{run.error}</p>
          {run.failure_details && run.failure_details.length > 0 && (
            <ul className="mt-2 space-y-1 text-xs text-red-700">
              {run.failure_details.slice(0, 20).map((d, i) => (
                <li key={i} className="font-mono">
                  {JSON.stringify(d)}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Output package */}
      {outputs.length > 0 && (
        <div
          className={`mt-6 rounded-lg border p-4 ${
            notSubmittable
              ? 'border-amber-300 bg-amber-50'
              : 'border-emerald-200 bg-emerald-50'
          }`}
        >
          <div className="flex items-center justify-between">
            <h2
              className={`text-sm font-semibold ${
                notSubmittable ? 'text-amber-900' : 'text-emerald-900'
              }`}
            >
              Output package
            </h2>
            {notSubmittable && (
              <span className="rounded-full bg-amber-200 px-2.5 py-0.5 text-xs font-semibold text-amber-900">
                Not submittable — validation failed
              </span>
            )}
          </div>
          {outputs.map((f) => (
            <div key={f.id} className="mt-2 flex items-center justify-between gap-4">
              <span
                className={`truncate font-mono text-xs ${
                  notSubmittable ? 'text-amber-800' : 'text-emerald-800'
                }`}
              >
                {f.filename}
              </span>
              <a
                href={runFileDownloadUrl(f.id)}
                className={`shrink-0 rounded-md px-3 py-1.5 text-xs font-medium text-white ${
                  notSubmittable
                    ? 'bg-amber-700 hover:bg-amber-800'
                    : 'bg-emerald-700 hover:bg-emerald-800'
                }`}
              >
                Download zip
              </a>
            </div>
          ))}
          {reports.map((f) => (
            <a
              key={f.id}
              href={runFileDownloadUrl(f.id)}
              className="mt-3 inline-block text-xs text-slate-600 underline hover:text-slate-900"
            >
              Download validation report
            </a>
          ))}
        </div>
      )}

      {/* Validation findings */}
      {findings.length > 0 && (
        <div className="mt-6">
          <h2 className="text-sm font-semibold text-slate-900">
            Validation findings{' '}
            <span className="font-normal text-slate-400">
              ({errorCount} error{errorCount === 1 ? '' : 's'} of {findings.length})
            </span>
          </h2>
          <div className="mt-3 overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs font-medium text-slate-500">
                  <th className="px-4 py-3">Severity</th>
                  <th className="px-4 py-3">Code</th>
                  <th className="px-4 py-3">Location</th>
                  <th className="px-4 py-3">Message</th>
                </tr>
              </thead>
              <tbody>
                {findings.map((f) => (
                  <tr key={f.id} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-3">
                      <SeverityBadge severity={f.severity} />
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-slate-700">
                      {f.code}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-500">
                      {findingLocation(f)}
                    </td>
                    <td className="px-4 py-3 text-slate-700">{f.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Input files */}
      <div className="mt-6">
        <h2 className="text-sm font-semibold text-slate-900">Input files</h2>
        {inputs.length === 0 ? (
          <p className="mt-2 text-sm text-slate-400">No input files.</p>
        ) : (
          <div className="mt-3 overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs font-medium text-slate-500">
                  <th className="px-4 py-3">Role</th>
                  <th className="px-4 py-3">File</th>
                  <th className="px-4 py-3">Checksum</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {inputs.map((f) => (
                  <tr key={f.id} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-3 text-slate-600">
                      {ROLE_LABELS[f.role] ?? f.role}
                    </td>
                    <td className="px-4 py-3 text-slate-800">{f.filename}</td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-400">
                      {f.checksum.slice(0, 12)}…
                    </td>
                    <td className="px-4 py-3 text-right">
                      <a
                        href={runFileDownloadUrl(f.id)}
                        className="text-xs text-slate-500 hover:text-slate-800 hover:underline"
                      >
                        download
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  )
}
