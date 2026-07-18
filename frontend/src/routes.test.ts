import { matchRoutes } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { routes } from './routes'

/** The path (or "index"/"*") of the route a URL resolves to. */
function leaf(url: string): string {
  const matches = matchRoutes(routes, url)
  if (!matches) return '(no match)'
  const route = matches[matches.length - 1].route
  if (route.index) return 'index'
  return route.path ?? '(no path)'
}

describe('route table', () => {
  it.each([
    // New routes → their pages.
    ['/', 'index'],
    ['/reporting', 'reporting'],
    ['/reporting/EBA', 'reporting/:regulatorCode'],
    ['/reporting/EBA/Liquidity', 'reporting/:regulatorCode/:category'],
    ['/reporting/suites/4', 'reporting/suites/:workflowId'],
    ['/reporting/runs/13', 'index'],
    ['/reporting/runs/13/input', 'input'],
    ['/reporting/runs/13/indicators', 'indicators'],
    ['/reporting/runs/13/validation', 'validation'],
    ['/reporting/runs/13/package', 'package'],
    ['/releases', 'releases'],
    ['/releases/regulators/2', 'releases/regulators/:regulatorId'],
    ['/releases/regulators/2/new', 'releases/regulators/:regulatorId/new'],
    ['/releases/1', 'releases/:snapshotId'],
    ['/reference', 'reference'],
    ['/reference/entities', 'reference/entities'],
    ['/reference/entities/2', 'reference/entities/:entityId'],
    ['/reference/filing-indicators', 'reference/filing-indicators'],
    ['/reference/parameters', 'reference/parameters'],
    ['/settings', 'settings'],
    ['/settings/reporting', 'settings/reporting'],
    ['/settings/reporting/EBA', 'settings/reporting/:regulatorCode'],
  ])('new route %s → %s', (url, expected) => {
    expect(leaf(url)).toBe(expected)
  })

  it.each([
    // Every pre-restructure URL pattern must hit a redirect, never the catch-all.
    ['/workflows', 'workflows'],
    ['/workflows/4', 'workflows/:workflowId'],
    ['/reporting/workflows/4', 'reporting/workflows/:workflowId'],
    ['/snapshots', 'snapshots'],
    ['/snapshots/1', 'snapshots/:snapshotId'],
    ['/runs', 'runs'],
    ['/runs/13', 'runs/:runId'],
  ])('legacy route %s → redirect %s', (url, expected) => {
    const resolved = leaf(url)
    expect(resolved).toBe(expected)
    expect(resolved).not.toBe('*')
  })

  it.each([
    ['/nope'],
    ['/reporting/suites/4/extra'],
    ['/reference/nope'],
    ['/deeply/unknown/path'],
  ])('unknown route %s → styled catch-all', (url) => {
    expect(leaf(url)).toBe('*')
  })
})
