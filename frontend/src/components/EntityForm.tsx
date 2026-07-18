import { useState } from 'react'
import type { Entity, EntityWrite } from '../api/workflows'
import { ErrorText, Select, fieldClass, primaryBtn, secondaryBtn } from './ui'

export default function EntityForm({
  initial,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial?: Entity
  submitLabel: string
  onSubmit: (body: EntityWrite) => Promise<void>
  onCancel?: () => void
}) {
  const [name, setName] = useState(initial?.name ?? '')
  const [lei, setLei] = useState(initial?.lei ?? '')
  const [country, setCountry] = useState(initial?.country ?? '')
  const [scope, setScope] = useState(initial?.default_scope ?? 'CON')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const valid =
    name.trim() !== '' && lei.trim().length === 20 && country.trim().length === 2

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      await onSubmit({
        name: name.trim(),
        lei: lei.trim().toUpperCase(),
        country: country.trim().toUpperCase(),
        default_scope: scope,
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1 sm:col-span-2">
          <span className="text-xs font-medium text-slate-600">Name</span>
          <input
            className={fieldClass}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Legal entity name"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs font-medium text-slate-600">
            LEI (20 chars)
          </span>
          <input
            className={`${fieldClass} font-mono`}
            value={lei}
            maxLength={20}
            onChange={(e) => setLei(e.target.value)}
            placeholder="213800XXXXXXXXXX0001"
          />
        </label>
        <div className="grid grid-cols-2 gap-4">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-slate-600">Country</span>
            <input
              className={`${fieldClass} font-mono uppercase`}
              value={country}
              maxLength={2}
              onChange={(e) => setCountry(e.target.value)}
              placeholder="GB"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs font-medium text-slate-600">Scope</span>
            <Select value={scope} onChange={setScope}>
              <option value="CON">Consolidated (CON)</option>
              <option value="IND">Individual (IND)</option>
            </Select>
          </label>
        </div>
      </div>

      <div className="mt-4 flex items-center gap-3">
        <button
          type="button"
          className={primaryBtn}
          disabled={!valid || busy}
          onClick={() => void submit()}
        >
          {busy ? 'Saving…' : submitLabel}
        </button>
        {onCancel && (
          <button type="button" className={secondaryBtn} onClick={onCancel}>
            Cancel
          </button>
        )}
        <ErrorText>{error}</ErrorText>
      </div>
    </div>
  )
}
