import { Card, EmptyState, PageHeader } from '../../components/ui'
import { runCrumbs, useRun } from './context'

export default function RunIndicators() {
  const ctx = useRun()
  const fis = ctx.detail.filing_indicators ?? []
  const filed = fis.filter((f) => f.reported)
  const notFiled = fis.filter((f) => !f.reported)

  return (
    <section>
      <PageHeader
        crumbs={runCrumbs(ctx, 'Filing Indicators')}
        title="Filing Indicators"
        subtitle={
          fis.length === 0
            ? undefined
            : `${filed.length} filed · ${notFiled.length} not filed`
        }
      />

      {fis.length === 0 ? (
        <EmptyState>Filing indicators were not derived for this run.</EmptyState>
      ) : (
        <Card className="overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-[11px] font-medium uppercase tracking-wide text-slate-400">
                <th className="px-4 py-2.5 font-medium">Template</th>
                <th className="px-4 py-2.5 font-medium">Filed</th>
                <th className="px-4 py-2.5 font-medium">Source</th>
              </tr>
            </thead>
            <tbody>
              {[...filed, ...notFiled].map((fi) => (
                <tr
                  key={fi.template_code}
                  className="border-b border-slate-100 last:border-0"
                >
                  <td className="px-4 py-2 font-mono text-xs text-slate-700">
                    {fi.template_code}
                  </td>
                  <td className="px-4 py-2">
                    <span
                      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium ${
                        fi.reported
                          ? 'bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-600/20'
                          : 'bg-slate-100 text-slate-500 ring-1 ring-inset ring-slate-500/15'
                      }`}
                    >
                      <span
                        className={`h-1.5 w-1.5 rounded-full ${
                          fi.reported ? 'bg-emerald-500' : 'bg-slate-400'
                        }`}
                      />
                      {fi.reported ? 'true' : 'false'}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-xs text-slate-500">
                    {fi.source === 'declared' ? 'Declared' : 'Auto (from facts)'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </section>
  )
}
