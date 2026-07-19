import { useMemo } from 'react'
import type { FactRow } from '../../api/workflows'
import { Block, EmptyState, PageHeader, SectionLabel, Skeleton } from '../../components/ui'
import { runCrumbs, useRun } from './context'

export default function RunInput() {
  const ctx = useRun()
  const { facts } = ctx

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
      <PageHeader crumbs={runCrumbs(ctx, 'Input Data')} title="Input Data" />

      {facts === null ? (
        <Skeleton className="h-40" />
      ) : groups.length === 0 ? (
        <EmptyState>No facts were submitted for this run.</EmptyState>
      ) : (
        <div className="space-y-6">
          {groups.map(([template, rows]) => (
            <div key={template}>
              <SectionLabel>{template}</SectionLabel>
              <Block className="mt-2.5 overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-[13px]">
                    <thead>
                      <tr className="border-b border-divider text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
                        <th className="px-6 py-2.5 font-semibold">Row</th>
                        <th className="px-6 py-2.5 font-semibold">Column</th>
                        <th className="px-6 py-2.5 text-right font-semibold">Value</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r, i) => (
                        <tr
                          key={i}
                          className="border-t border-divider font-mono tabular-nums text-sub first:border-t-0"
                        >
                          <td className="px-6 py-2">{r.row_code}</td>
                          <td className="px-6 py-2">{r.column_code}</td>
                          <td className="px-6 py-2 text-right text-data">{r.value}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Block>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
