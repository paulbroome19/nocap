import type { Verdict } from '../api/workflows'

// Tone by verdict — blocking failures read red, non-blocking amber, clean
// emerald, in-progress a pulsing amber. Monochrome base + existing status hues.
function tone(v: Verdict): { ring: string; dot: string; pulse: boolean } {
  if (v.submittable === null)
    return { ring: 'border-amber-200 bg-amber-50', dot: 'bg-amber-500', pulse: true }
  if (v.status === 'failed')
    return { ring: 'border-red-200 bg-red-50', dot: 'bg-red-500', pulse: false }
  if (!v.submittable)
    return { ring: 'border-red-200 bg-red-50', dot: 'bg-red-500', pulse: false }
  if (v.non_blocking_failures > 0 || v.warnings > 0)
    return { ring: 'border-amber-200 bg-amber-50', dot: 'bg-amber-500', pulse: false }
  return { ring: 'border-emerald-200 bg-emerald-50', dot: 'bg-emerald-500', pulse: false }
}

/**
 * The submission verdict, with its reasoning always stated. A green banner over
 * red rows is impossible: the reasoning line carries the blocking/non-blocking
 * counts that justify the headline.
 */
export default function VerdictBanner({ verdict }: { verdict: Verdict }) {
  const t = tone(verdict)
  return (
    <div className={`rounded-lg border px-4 py-3 ${t.ring}`}>
      <div className="flex items-center gap-2.5">
        <span
          className={`h-2.5 w-2.5 shrink-0 rounded-full ${t.dot} ${
            t.pulse ? 'animate-pulse' : ''
          }`}
        />
        <span className="text-sm font-semibold text-slate-900">{verdict.label}</span>
        <span className="text-slate-300">·</span>
        <span className="text-sm text-slate-600">{verdict.reasoning}</span>
      </div>
      {!verdict.severity_known && (
        <p className="mt-1.5 pl-5 text-xs text-slate-500">
          Some failing rules have no declared severity; they are treated as
          non-blocking but shown separately above.
        </p>
      )}
    </div>
  )
}
