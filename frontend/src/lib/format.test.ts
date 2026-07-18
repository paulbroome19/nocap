import { describe, expect, it } from 'vitest'
import { formatDate, formatTime } from './format'
import { runStatusLabel } from './status'

describe('formatDate', () => {
  it.each([
    ['2025-12-31', '31 Dec 2025'],
    ['2025-01-05', '05 Jan 2025'],
    ['2026-07-18', '18 Jul 2026'],
    // ISO datetime → formatted from the calendar date, no timezone shift.
    ['2025-12-31T23:30:00.000Z', '31 Dec 2025'],
    ['2026-07-18T00:00:00+02:00', '18 Jul 2026'],
  ])('%s → %s', (iso, expected) => {
    expect(formatDate(iso)).toBe(expected)
  })

  it('handles empty / invalid gracefully', () => {
    expect(formatDate(null)).toBe('')
    expect(formatDate('')).toBe('')
    expect(formatDate('not-a-date')).toBe('not-a-date')
  })
})

describe('formatTime', () => {
  it('is empty for missing/invalid input', () => {
    expect(formatTime(null)).toBe('')
    expect(formatTime('nope')).toBe('')
  })
  it('returns HH:mm for a valid datetime', () => {
    expect(formatTime('2025-12-31T14:03:00')).toMatch(/^\d{2}:\d{2}$/)
  })
})

describe('runStatusLabel (display vocabulary)', () => {
  it.each([
    ['generated', 'Successful'],
    ['failed_validation', 'Failed'],
    ['failed', 'Failed'],
    ['running', 'Running'],
    ['formula_validation_running', 'Validating'],
    ['created', 'Draft'],
    ['files_attached', 'Draft'],
  ] as const)('%s → %s', (status, label) => {
    expect(runStatusLabel(status)).toBe(label)
  })
})
