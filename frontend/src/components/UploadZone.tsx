import { useId, useRef, useState } from 'react'

/**
 * Upload zone (design-spec §7): dashed faint border, 10px radius, "Drop file or
 * browse" label, a file-type descriptor beneath. Controlled — the parent owns
 * the selected file. The user's filename is display only.
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
        'flex cursor-pointer flex-col items-center justify-center rounded-[10px] border border-dashed text-center transition-colors',
        compact ? 'gap-1 px-4 py-[13px]' : 'gap-1.5 px-6 py-[22px]',
        disabled
          ? 'cursor-not-allowed border-field bg-canvas opacity-60'
          : dragging
            ? 'border-sub bg-hover'
            : 'border-faint bg-page hover:bg-hover',
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
      {file ? (
        <span className="max-w-full truncate font-mono text-[12px] text-data">
          {file.name}
        </span>
      ) : (
        <>
          <span className="text-[12px] font-semibold text-data">
            {dragging ? 'Drop to upload' : 'Drop file or browse'}
          </span>
          {hint && (
            <span className="text-[12.5px] text-sub">
              <span className="font-mono">{hint}</span> file
            </span>
          )}
        </>
      )}
    </div>
  )
}
