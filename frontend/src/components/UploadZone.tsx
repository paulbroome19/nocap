import { useId, useRef, useState } from 'react'

/**
 * A drag-and-drop upload zone with hover/active states, a file-type hint, and a
 * selected-file chip. Replaces bare `<input type=file>` across the reporting
 * surface. Controlled: the parent owns the selected `file`.
 */
export default function UploadZone({
  accept,
  onFile,
  file,
  hint,
  disabled = false,
  compact = false,
}: {
  accept: string
  onFile: (file: File | null) => void
  file: File | null
  hint?: string
  disabled?: boolean
  compact?: boolean
}) {
  const inputId = useId()
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  function take(list: FileList | null) {
    if (disabled) return
    const f = list?.[0] ?? null
    if (f) onFile(f)
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        if (!disabled) setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        take(e.dataTransfer.files)
      }}
      onClick={() => !disabled && inputRef.current?.click()}
      role="button"
      tabIndex={disabled ? -1 : 0}
      onKeyDown={(e) => {
        if ((e.key === 'Enter' || e.key === ' ') && !disabled) {
          e.preventDefault()
          inputRef.current?.click()
        }
      }}
      aria-disabled={disabled}
      className={[
        'group flex cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed text-center transition-colors',
        compact ? 'gap-1 px-4 py-4' : 'gap-1.5 px-6 py-8',
        disabled
          ? 'cursor-not-allowed border-slate-200 bg-slate-50 opacity-60'
          : dragging
            ? 'border-slate-900 bg-slate-50'
            : 'border-slate-300 bg-white hover:border-slate-400 hover:bg-slate-50/60',
      ].join(' ')}
    >
      <input
        id={inputId}
        ref={inputRef}
        type="file"
        accept={accept}
        disabled={disabled}
        className="sr-only"
        onChange={(e) => {
          take(e.target.files)
          e.target.value = ''
        }}
      />
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        className={`${compact ? 'h-5 w-5' : 'h-7 w-7'} text-slate-400 transition-colors group-hover:text-slate-500`}
      >
        <path
          d="M12 16V4m0 0L8 8m4-4l4 4M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      {file ? (
        <span className="max-w-full truncate font-mono text-xs text-slate-700">
          {file.name}
        </span>
      ) : (
        <>
          <span className="text-sm font-medium text-slate-600">
            {dragging ? 'Drop to upload' : 'Drag a file here, or click to browse'}
          </span>
          {hint && (
            <span className="text-[11px] uppercase tracking-wide text-slate-400">
              {hint}
            </span>
          )}
        </>
      )}
    </div>
  )
}
