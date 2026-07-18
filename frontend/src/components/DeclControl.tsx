import type { Declaration } from '../api/workflows'

// The three filing-indicator states. Optional is the default (derive from
// facts); Required forces a positive indicator and fails the run if empty; Not
// required declares not-filed and excludes the template's facts.
const DECL_OPTIONS: { v: Declaration; label: string }[] = [
  { v: 'required', label: 'Required' },
  { v: 'optional', label: 'Optional' },
  { v: 'not_required', label: 'Not required' },
]

const DECL_ACTIVE: Record<Declaration, string> = {
  required: 'bg-emerald-600 text-white',
  optional: 'bg-slate-900 text-white',
  not_required: 'bg-amber-500 text-white',
}

export default function DeclControl({
  value,
  onChange,
  disabled = false,
}: {
  value: Declaration
  onChange: (v: Declaration) => void
  disabled?: boolean
}) {
  return (
    <div className="inline-flex overflow-hidden rounded-md border border-slate-300">
      {DECL_OPTIONS.map((o, i) => (
        <button
          key={o.v}
          type="button"
          disabled={disabled}
          onClick={() => onChange(o.v)}
          className={[
            'px-2.5 py-1 text-xs font-medium transition-colors disabled:opacity-50',
            i > 0 ? 'border-l border-slate-300' : '',
            value === o.v
              ? DECL_ACTIVE[o.v]
              : 'bg-white text-slate-600 hover:bg-slate-50',
          ].join(' ')}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
