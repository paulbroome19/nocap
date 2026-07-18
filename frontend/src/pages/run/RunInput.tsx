import { useMemo } from 'react'
import type { FactRow } from '../../api/workflows'
import { Card, EmptyState, PageHeader, Skeleton } from '../../components/ui'
import { runCrumbs, useRun } from './context'

export default function RunInput() {
  const ctx = useRun()
  const { facts, detail } = ctx

  const groups = useMemo(() => {
    const m = new Map<string, FactRow[]>()
    for (const f of facts ?? []) {
      const arr = m.get(f.template_code)
      if (arr) arr.push(f)
      else m.set(f.template_code, [f])
    }
    return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0]))
  }, [facts])

  return (
    <section>
      <PageHeader
        crumbs={runCrumbs(ctx, 'Input Data')}
        title="Input Data"
        subtitle={
          facts === null
            ? undefined
            : `${detail.fact_count} facts across ${groups.length} templates`
        }
      />

      {facts === null ? (
        <Skeleton className="h-40" />
      ) : groups.length === 0 ? (
        <EmptyState>No facts ingested for this run.</EmptyState>
      ) : (
        <div className="space-y-3">
          {groups.map(([template, rows]) => (
            <Card key={template} className="overflow-hidden">
              <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50/70 px-4 py-2.5">
                <span className="font-mono text-xs font-semibold text-slate-700">
                  {template}
                </span>
                <span className="text-xs tabular-nums text-slate-400">
                  {rows.length} {rows.length === 1 ? 'cell' : 'cells'}
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-[11px] font-medium uppercase tracking-wide text-slate-400">
                      <th className="px-4 py-2 font-medium">Row</th>
                      <th className="px-4 py-2 font-medium">Column</th>
                      <th className="px-4 py-2 text-right font-medium">Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r, i) => (
                      <tr
                        key={i}
                        className="border-t border-slate-50 font-mono text-xs tabular-nums text-slate-600"
                      >
                        <td className="px-4 py-1.5">{r.row_code}</td>
                        <td className="px-4 py-1.5">{r.column_code}</td>
                        <td className="px-4 py-1.5 text-right text-slate-800">
                          {r.value}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          ))}
        </div>
      )}
    </section>
  )
}
