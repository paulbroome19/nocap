import type { Verdict } from '../api/workflows'
import { Block } from './ui'

/**
 * The submission verdict, carried under a gold rule (§8: gold = the verdict
 * rule). The reasoning is always stated; a non-zero blocking count is the one
 * sanctioned red on this block (failure count). Neutral otherwise.
 */
export default function VerdictBanner({ verdict }: { verdict: Verdict }) {
  const blocking = verdict.blocking
  return (
    <Block className="p-6">
      {/* Gold verdict rule */}
      <div className="mb-4 h-[3px] w-12 bg-gold" />
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className="text-[18px] font-bold tracking-[-0.01em] text-ink">
          {verdict.label}
        </span>
        {blocking > 0 && (
          <span className="text-[13px] font-semibold text-red">
            {blocking} blocking
          </span>
        )}
      </div>
      <p className="mt-2 max-w-2xl text-[14px] text-sub">{verdict.reasoning}</p>
      {!verdict.severity_known && (
        <p className="mt-2 text-[13px] text-muted">
          Some failing rules have no declared severity; they are treated as
          non-blocking and shown separately.
        </p>
      )}
    </Block>
  )
}
