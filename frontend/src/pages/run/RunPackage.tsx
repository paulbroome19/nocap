import { useState } from 'react'
import { downloadRunFile, type RunFile } from '../../api/workflows'
import {
  Card,
  EmptyState,
  ErrorText,
  PageHeader,
  primaryBtn,
} from '../../components/ui'
import { formatDate } from '../../lib/format'
import { runCrumbs, useRun } from './context'

const ROLE_LABEL: Record<string, string> = {
  package_output: 'Submission package',
  validation_report: 'Validation report',
  fact_input: 'Fact file',
  indicators_params: 'Indicators / parameters',
}

function bytes(n: number | null): string {
  if (n === null) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

export default function RunPackage() {
  const ctx = useRun()
  const files = ctx.detail.files
  const pkg = files.find((f) => f.role === 'package_output')
  const [error, setError] = useState<string | null>(null)

  async function download(f: RunFile) {
    setError(null)
    try {
      await downloadRunFile(f.id, f.filename)
    } catch (e) {
      setError(
        `Could not download ${f.filename}: ${
          e instanceof Error ? e.message : String(e)
        }`,
      )
      ctx.reload()
    }
  }

  return (
    <section className="space-y-6">
      <PageHeader crumbs={runCrumbs(ctx, 'Package')} title="Package" />

      <ErrorText>{error}</ErrorText>

      <Card className="p-5">
        {pkg ? (
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="min-w-0">
              <div className="truncate font-mono text-sm text-slate-800">
                {pkg.filename}
              </div>
              <div className="mt-0.5 text-xs text-slate-400">
                {bytes(pkg.size_bytes)}
              </div>
            </div>
            {pkg.available ? (
              <button
                type="button"
                className={primaryBtn}
                onClick={() => void download(pkg)}
              >
                Download package
              </button>
            ) : (
              <span className="rounded-md bg-slate-100 px-4 py-1.5 text-sm font-medium text-slate-400">
                Unavailable
              </span>
            )}
          </div>
        ) : (
          <EmptyState>No package was generated for this run.</EmptyState>
        )}
      </Card>

      <div>
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
          All files
        </h2>
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-[11px] font-medium uppercase tracking-wide text-slate-400">
                <th className="px-4 py-2.5 font-medium">Role</th>
                <th className="px-4 py-2.5 font-medium">File</th>
                <th className="px-4 py-2.5 font-medium">Added</th>
                <th className="px-4 py-2.5 text-right font-medium">Download</th>
              </tr>
            </thead>
            <tbody>
              {files.map((f) => (
                <tr key={f.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-2 text-xs text-slate-600">
                    {ROLE_LABEL[f.role] ?? f.role}
                  </td>
                  <td className="px-4 py-2 font-mono text-xs text-slate-700">
                    {f.filename}
                  </td>
                  <td className="px-4 py-2 text-xs tabular-nums text-slate-400">
                    {formatDate(f.created_at)}
                  </td>
                  <td className="px-4 py-2 text-right">
                    {f.available ? (
                      <button
                        type="button"
                        className="text-xs font-medium text-slate-600 underline-offset-2 hover:text-slate-900 hover:underline"
                        onClick={() => void download(f)}
                      >
                        Download
                      </button>
                    ) : (
                      <span className="text-xs text-slate-300">unavailable</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
    </section>
  )
}
