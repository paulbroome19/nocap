import VerdictBanner from '../../components/VerdictBanner'
import { Card, PageHeader } from '../../components/ui'
import { runCrumbs, useRun } from './context'

// Interim validation view — verdict + a flat register. The regulatory rebuild
// (blocking-first grouping, collapsed passed, per-evaluation detail) follows.
const RESULT_STYLE: Record<string, string> = {
  PASSED: 'bg-emerald-50 text-emerald-700',
  FAILED: 'bg-red-50 text-red-700',
  WARNING: 'bg-amber-50 text-amber-700',
  NOTE: 'bg-sky-50 text-sky-700',
  DEACTIVATED: 'bg-slate-100 text-slate-500',
}

export default function RunValidation() {
  const ctx = useRun()
  const { detail } = ctx
  const rows = detail.rule_register

  return (
    <section className="space-y-5">
      <PageHeader crumbs={runCrumbs(ctx, 'Validation')} title="Validation" />

      <VerdictBanner verdict={detail.verdict} />

      <Card className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-[11px] font-medium uppercase tracking-wide text-slate-400">
              <th className="px-4 py-2.5 font-medium">ID</th>
              <th className="px-4 py-2.5 font-medium">Rule</th>
              <th className="px-4 py-2.5 font-medium">Result</th>
              <th className="px-4 py-2.5 font-medium">Detail</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-b border-slate-100 align-top last:border-0">
                <td className="whitespace-nowrap px-4 py-2 font-mono text-xs text-slate-700">
                  {r.id}
                </td>
                <td className="px-4 py-2 text-slate-700">{r.rule}</td>
                <td className="px-4 py-2">
                  <span
                    className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${
                      RESULT_STYLE[r.result] ?? RESULT_STYLE.NOTE
                    }`}
                  >
                    {r.result}
                  </span>
                </td>
                <td className="px-4 py-2 text-xs text-slate-500">
                  {r.detail}
                  {(r.rule_text || r.description) && (
                    <div className="mt-0.5 text-[11px] text-slate-400">
                      {r.rule_text ?? r.description}
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </section>
  )
}
