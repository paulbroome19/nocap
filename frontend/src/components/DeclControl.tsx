import type { Declaration } from '../api/workflows'

// The three filing-indicator states. Optional is the default (derive from
// facts); Required forces a positive indicator and fails the run if empty; Not
// required declares not-filed and excludes the template's facts. A neutral
// segmented control — the active option is ink, distinction is by label/position
// (red/gold law: no decorative colour).
const DECL_OPTIONS: { v: Declaration; label: string }[] = [
  { v: 'required', label: 'Required' },
  { v: 'optional', label: 'Optional' },
  { v: 'not_required', label: 'Not required' },
]

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
    <div className="inline-flex overflow-hidden rounded-[9px] border border-field">
      {DECL_OPTIONS.map((o, i) => (
        <button
          key={o.v}
          type="button"
          disabled={disabled}
          onClick={() => onChange(o.v)}
          className={[
            'px-3 py-1.5 text-[12px] font-medium transition-colors disabled:opacity-50',
            i > 0 ? 'border-l border-field' : '',
            value === o.v
              ? 'bg-ink text-white'
              : 'bg-page text-sub hover:bg-hover',
          ].join(' ')}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
