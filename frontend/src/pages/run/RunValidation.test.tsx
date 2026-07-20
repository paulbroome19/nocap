// @vitest-environment jsdom
//
// The validation screen is organised by rule *family* (Formula / Filing &
// structural / Informational), never by severity, and the formula section is
// never rendered green when zero rules evaluated. These pin that structure.

import { MemoryRouter, Outlet, Route, Routes } from 'react-router-dom'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it } from 'vitest'

afterEach(cleanup)
import RunValidation from './RunValidation'
import type { RunCtx } from './context'
import type { FormulaSummary, RegisterRow } from '../../api/workflows'

function ctxWith(
  rows: RegisterRow[],
  formula: FormulaSummary | null = null,
): RunCtx {
  return {
    id: 1,
    regulatorCode: 'EBA',
    config: { name: 'COREP LCR', category: 'Liquidity' },
    detail: {
      run: { reference_date: '2025-12-31', workflow_id: 3, rule_scope: null },
      files: [],
      rule_register: rows,
      formula_summary: formula,
      verdict: {
        label: 'Not submittable',
        blocking: 1,
        reasoning: '1 blocking error',
        severity_known: true,
      },
    },
  } as unknown as RunCtx
}

function renderScreen(ctx: RunCtx) {
  return render(
    <MemoryRouter initialEntries={['/v']}>
      <Routes>
        <Route element={<Outlet context={ctx} />}>
          <Route path="/v" element={<RunValidation />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  )
}

const formulaFail: RegisterRow = {
  id: 'v16053_m',
  rule: 'Value Assertion',
  source: 'formula',
  template: 'C_72.00.a',
  data_evaluated: '{C_72.00.a,0010,0010,} 57621 >= 66241',
  result: 'FAILED',
  detail: 'assertion not satisfied',
  rule_text: '{C 72.00.a, r0010} >= {C 76.00, r0010}',
  severity: 'error',
  blocking: true,
  evaluations: [
    {
      message: 'Fails because 57621 >= 66241 is not true.',
      values: '57621 >= 66241',
      template_code: 'C_72.00.a',
      row_code: '0010',
      column_code: '0010',
    },
  ],
  satisfied: 0,
  not_satisfied: 1,
}
const formulaPass = (id: string): RegisterRow => ({
  id,
  rule: 'Value Assertion',
  source: 'formula',
  template: null,
  data_evaluated: '5 evaluation(s)',
  result: 'PASSED',
  detail: '',
  rule_text: '{C 72.00.a, r0020} = {C 76.00, r0020}',
  severity: 'warning',
  satisfied: 5,
  not_satisfied: 0,
  evaluations: null,
})
const structFail: RegisterRow = {
  id: 'FR 1.7.1',
  rule: 'A template with facts has a positive filing indicator',
  source: 'structural',
  template: 'C_73.00',
  data_evaluated: 'C_73.00',
  result: 'FAILED',
  detail: 'missing filing indicator',
  description: 'Every template that carries data must declare an indicator.',
  severity: 'error',
  blocking: true,
}
const structPass: RegisterRow = {
  id: 'FR 3.2(b)',
  rule: 'Percentages reported as ratios',
  source: 'structural',
  template: null,
  data_evaluated: 'Percentage facts',
  result: 'PASSED',
  detail: '',
  description: 'EBA percentage datapoints are filed as ratios.',
  severity: null,
}
const noteRow: RegisterRow = {
  id: 'NC-S17',
  rule: 'Entry-point verified',
  source: 'structural',
  template: null,
  data_evaluated: 'Package',
  result: 'NOTE',
  detail: 'derived by pattern',
  description: 'The entry point was derived, not verified.',
  severity: 'info',
}

describe('RunValidation — sections by family', () => {
  const rows = [
    formulaFail,
    formulaPass('vA_m'),
    formulaPass('vB_m'),
    structFail,
    structPass,
    noteRow,
  ]

  it('renders three family sections with per-section counts', () => {
    renderScreen(ctxWith(rows))
    expect(screen.getByText('Formula validations')).toBeTruthy()
    expect(screen.getByText('Filing & structural checks')).toBeTruthy()
    // Per-section summary line, e.g. "Formula: 2/3 passed · 1 failed".
    expect(screen.getByText(/Formula: 2\/3 passed · 1 failed/)).toBeTruthy()
    expect(screen.getByText(/Structural: 1\/2 passed · 1 failed/)).toBeTruthy()
    expect(screen.getByText(/Informational: 1/)).toBeTruthy()
  })

  it('opens formula by default and collapses structural', async () => {
    renderScreen(ctxWith(rows))
    // Formula rows are visible immediately (default-open headline section).
    expect(screen.getByText('v16053_m')).toBeTruthy()
    // Structural rows are hidden until the section is expanded.
    expect(screen.queryByText('FR 1.7.1')).toBeNull()
    await userEvent.click(
      screen.getByRole('button', { name: /Filing & structural checks/ }),
    )
    await waitFor(() => expect(screen.getByText('FR 1.7.1')).toBeTruthy())
  })

  it('shows a severity badge (blocking) and expands a formula row to the comparison', async () => {
    renderScreen(ctxWith(rows))
    expect(screen.getAllByText('Blocking').length).toBeGreaterThan(0)
    // Expand the failed formula row → the evaluated comparison from Arelle.
    await userEvent.click(screen.getByText('v16053_m'))
    await waitFor(() => {
      expect(screen.getByText('Evaluated comparison')).toBeTruthy()
      expect(screen.getByText('57621 >= 66241')).toBeTruthy()
    })
  })
})

describe('RunValidation — formula section never green when empty', () => {
  it('shows a failure callout when formula evaluated zero rules', () => {
    const formula: FormulaSummary = {
      status: 'executed',
      loaded: 500,
      evaluated: 0,
      satisfied: 0,
      unsatisfied: 0,
      deactivated: [],
      note: 'the taxonomy package likely omits the formula linkbase',
    }
    renderScreen(ctxWith([structPass], formula))
    expect(
      screen.getByText(/Formula validation completed but evaluated 0 rules/),
    ).toBeTruthy()
    // Not a green pass: the count line reflects zero.
    expect(screen.getByText(/Formula: 0\/0 passed/)).toBeTruthy()
  })
})
