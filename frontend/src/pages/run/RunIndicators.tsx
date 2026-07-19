import { Block, EmptyState, PageHeader } from '../../components/ui'
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
      />

      {fis.length === 0 ? (
        <EmptyState>Filing indicators were not derived for this run.</EmptyState>
      ) : (
        <Block className="overflow-hidden">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-divider text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
                <th className="px-6 py-2.5 font-semibold">Template</th>
                <th className="px-6 py-2.5 font-semibold">Filing</th>
                <th className="px-6 py-2.5 font-semibold">Source</th>
              </tr>
            </thead>
            <tbody>
              {[...filed, ...notFiled].map((fi) => (
                <tr
                  key={fi.template_code}
                  className="border-t border-divider first:border-t-0"
                >
                  <td className="px-6 py-2.5 font-mono text-data">
                    {fi.template_code}
                  </td>
                  <td className="px-6 py-2.5">
                    <span className="inline-flex items-center gap-2 text-data">
                      <span
                        className={`h-1.5 w-1.5 rounded-full ${
                          fi.reported ? 'bg-ink' : 'bg-faint'
                        }`}
                      />
                      {fi.reported ? 'Filed' : 'Not filed'}
                    </span>
                  </td>
                  <td className="px-6 py-2.5 text-sub">
                    {fi.source === 'auto'
                      ? 'Optional (from facts)'
                      : fi.reported
                        ? 'Required (declared)'
                        : 'Not required (declared)'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Block>
      )}
    </section>
  )
}
