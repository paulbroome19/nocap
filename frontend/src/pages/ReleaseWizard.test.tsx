// @vitest-environment jsdom
//
// Regression guard for the PRODUCT.md rule: the user must never be left on a
// spinner after the backend has finished. The wizard uploads, then polls the
// release until it is `ready` and navigates to it. A `cancelled` ref bug made
// the poll never run under React Strict Mode (dev), so the "converting" spinner
// stuck forever even though the release was ready. This test renders the wizard
// exactly as main.tsx does — inside <StrictMode> — and asserts the poll runs and
// navigation happens.

import { StrictMode } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ReleaseWizard from './ReleaseWizard'
import { createRelease, getSnapshotOrNull } from '../api/snapshots'

vi.mock('../api/snapshots', () => ({
  getRegulator: vi
    .fn()
    .mockResolvedValue({ id: 1, code: 'EBA', name: 'European Banking Authority' }),
  // Upload succeeds; the release comes back still converting (`ingesting`).
  createRelease: vi.fn(
    (
      _id: number,
      _label: string,
      _files: unknown,
      onProgress?: (f: number) => void,
    ) => {
      onProgress?.(1)
      return Promise.resolve({ id: 7, status: 'ingesting' })
    },
  ),
  getSnapshotOrNull: vi.fn(),
}))

function renderWizard() {
  return render(
    <StrictMode>
      <MemoryRouter initialEntries={['/releases/regulators/1/new']}>
        <Routes>
          <Route
            path="/releases/regulators/:regulatorId/new"
            element={<ReleaseWizard />}
          />
          <Route path="/releases/:id" element={<div>release detail page</div>} />
        </Routes>
      </MemoryRouter>
    </StrictMode>,
  )
}

async function fillAndSubmit() {
  const user = userEvent.setup()
  await user.type(screen.getByPlaceholderText(/4\.2/), '4.2')
  const inputs = document.querySelectorAll('input[type=file]')
  expect(inputs).toHaveLength(3)
  await user.upload(inputs[0] as HTMLInputElement, new File(['x'], 'rules.xlsx'))
  await user.upload(inputs[1] as HTMLInputElement, new File(['x'], 'dpm.accdb'))
  await user.upload(inputs[2] as HTMLInputElement, new File(['x'], 'taxo.zip'))
  await user.click(screen.getByRole('button', { name: /create/i }))
}

describe('ReleaseWizard — never stuck on the converting spinner', () => {
  beforeEach(() => vi.clearAllMocks())

  it('polls the release under Strict Mode and navigates once it is ready', async () => {
    // First poll: still converting; second: ready. Exercises the loop across
    // the ingesting → ready transition.
    ;(getSnapshotOrNull as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ id: 7, status: 'ingesting' })
      .mockResolvedValue({ id: 7, status: 'ready' })

    renderWizard()
    await fillAndSubmit()

    expect(createRelease).toHaveBeenCalledTimes(1)
    // The bug left `cancelled` stuck true, so the poll never fired. It must fire.
    await waitFor(() => expect(getSnapshotOrNull).toHaveBeenCalled(), {
      timeout: 12000,
    })
    // And once ready, it navigates to the release detail page — no dead spinner.
    await waitFor(
      () => expect(screen.getByText(/release detail page/i)).toBeTruthy(),
      { timeout: 12000 },
    )
  }, 20000)

  it('surfaces a failure (release purged → 404) instead of spinning forever', async () => {
    ;(getSnapshotOrNull as ReturnType<typeof vi.fn>).mockResolvedValue(null)

    renderWizard()
    await fillAndSubmit()

    await waitFor(
      () => expect(screen.getByText(/could not be completed/i)).toBeTruthy(),
      { timeout: 12000 },
    )
  }, 20000)
})
