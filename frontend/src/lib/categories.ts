// The curated category display order (matches the backend WORKFLOW_CATEGORIES).
// Reporting, Settings, and any category list render in this fixed order.
export const CATEGORY_ORDER = [
  'Capital',
  'Liquidity',
  'Financial',
  'Last Mile Reporting',
] as const

/** Sort keys by the fixed category order; unknown categories fall to the end. */
export function byCategoryOrder<T>(items: T[], key: (t: T) => string): T[] {
  const rank = (c: string) => {
    const i = (CATEGORY_ORDER as readonly string[]).indexOf(c)
    return i === -1 ? CATEGORY_ORDER.length : i
  }
  return [...items].sort((a, b) => rank(key(a)) - rank(key(b)))
}
