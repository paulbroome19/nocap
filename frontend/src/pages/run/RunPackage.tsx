import { useState } from 'react'
import { downloadRunFile, type RunFile } from '../../api/workflows'
import {
  Block,
  EmptyState,
  ErrorText,
  PageHeader,
  SectionLabel,
  secondaryBtn,
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
    <section className="space-y-8">
      <PageHeader crumbs={runCrumbs(ctx, 'Package')} title="Package" />

      <ErrorText>{error}</ErrorText>

      <Block className="p-6">
        {pkg ? (
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="min-w-0">
              <div className="truncate font-mono text-[14px] text-data">
                {pkg.filename}
              </div>
              <div className="mt-0.5 text-[12px] text-muted">
                {bytes(pkg.size_bytes)}
              </div>
            </div>
            {pkg.available ? (
              <button
                type="button"
                className={secondaryBtn}
                onClick={() => void download(pkg)}
              >
                Download package
              </button>
            ) : (
              <span className="rounded-[9px] bg-canvas px-4 py-1.5 text-[13px] font-medium text-muted">
                Unavailable
              </span>
            )}
          </div>
        ) : (
          <EmptyState>No package was generated for this run.</EmptyState>
        )}
      </Block>

      <div>
        <SectionLabel>All files</SectionLabel>
        <Block className="mt-2.5 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-divider text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
                  <th className="px-6 py-2.5 font-semibold">Role</th>
                  <th className="px-6 py-2.5 font-semibold">File</th>
                  <th className="px-6 py-2.5 font-semibold">Added</th>
                  <th className="px-6 py-2.5 text-right font-semibold">Download</th>
                </tr>
              </thead>
              <tbody>
                {files.map((f) => (
                  <tr key={f.id} className="border-t border-divider first:border-t-0">
                    <td className="px-6 py-2.5 text-sub">
                      {ROLE_LABEL[f.role] ?? f.role}
                    </td>
                    <td className="px-6 py-2.5 font-mono text-[12px] text-data">
                      {f.filename}
                    </td>
                    <td className="px-6 py-2.5 tabular-nums text-muted">
                      {formatDate(f.created_at)}
                    </td>
                    <td className="px-6 py-2.5 text-right">
                      {f.available ? (
                        <button
                          type="button"
                          className="text-[13px] font-medium text-sub underline-offset-2 hover:text-data hover:underline"
                          onClick={() => void download(f)}
                        >
                          Download
                        </button>
                      ) : (
                        <span className="text-[12px] text-faint">unavailable</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Block>
      </div>
    </section>
  )
}
