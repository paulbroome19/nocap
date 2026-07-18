// Shared formatting helpers. Every rendered date goes through formatDate so the
// app shows one format everywhere: DD MMM YYYY (e.g. "31 Dec 2025").

const MONTHS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
]

/** "2025-12-31" | ISO datetime → "31 Dec 2025" (timezone-safe for date-only). */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return ''
  // Date-only or ISO prefix: format from the calendar parts, no tz shift.
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  if (m) return `${m[3]} ${MONTHS[Number(m[2]) - 1]} ${m[1]}`
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const day = String(d.getDate()).padStart(2, '0')
  return `${day} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`
}

/** Local time HH:mm — used as a muted tiebreaker where dates/keys collide. */
export function formatTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return `${String(d.getHours()).padStart(2, '0')}:${String(
    d.getMinutes(),
  ).padStart(2, '0')}`
}
