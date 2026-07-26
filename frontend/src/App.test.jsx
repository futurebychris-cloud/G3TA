import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import App from './App.jsx'
import { AccessibilityProvider } from './accessibility/AccessibilityContext.jsx'
import { ACCESSIBILITY_STORAGE_KEY } from './accessibility/AccessibilityContext.jsx'
import { TextToSpeechProvider } from './hooks/useTextToSpeech.js'

const apiMocks = vi.hoisted(() => ({
  streamPlan: vi.fn(),
  finalizePlan: vi.fn(),
  cancelPlan: vi.fn().mockResolvedValue({ status: 'finished' }),
}))

vi.mock('./api.js', () => ({
  getHealth: vi.fn().mockResolvedValue({ status: 'ok', dependencies: {} }),
  loadLatestResult: vi.fn().mockRejectedValue(new Error('No saved result')),
  saveResult: vi.fn().mockResolvedValue({ trip_id: 'test-saved-trip-123456' }),
  cancelPlan: apiMocks.cancelPlan,
  streamPlan: apiMocks.streamPlan,
  finalizePlan: apiMocks.finalizePlan,
}))

function renderApp() {
  localStorage.setItem(ACCESSIBILITY_STORAGE_KEY, JSON.stringify({ onboardingComplete: true }))
  return render(
    <AccessibilityProvider>
      <TextToSpeechProvider><App /></TextToSpeechProvider>
    </AccessibilityProvider>,
  )
}

describe('app accessibility entry point', () => {
  it('shows the accessibility button in the header and opens its options', async () => {
    const user = userEvent.setup()
    renderApp()
    const header = screen.getByRole('banner')
    const trigger = screen.getByRole('button', { name: 'Accessibility options' })
    expect(header).toContainElement(trigger)
    await user.click(trigger)
    expect(screen.getByRole('dialog', { name: 'Accessibility options' })).toBeVisible()
    expect(screen.getByRole('checkbox', { name: /Bigger Text/ })).toBeEnabled()
    expect(screen.getByRole('radio', { name: 'Senior Mode' })).toBeEnabled()
  })
})

describe('planning flow', () => {
  it('opens the full preview immediately when all agents complete', async () => {
    window.scrollTo = vi.fn()
    const result = {
      destination: 'Shanghai',
      dates: { start: '2026-07-30', end: '2026-08-03' },
      summary: 'A five-day Shanghai journey.',
      cost: {
        currency: 'USD',
        total: 1200,
        budget: 2500,
        within_budget: true,
        breakdown: { transportation: 700, food: 300, activity: 200 },
        expense_items: [],
      },
      agent_outputs: { budget: {}, planning: {} },
      schedule: [],
      map_points: [],
      packing_list: [],
      reasoning_log: [],
    }
    apiMocks.streamPlan.mockImplementation(async (_input, onEvent) => {
      onEvent({ type: 'agent_start', agent: 'transportation' })
      onEvent({ type: 'agent_done', agent: 'transportation' })
      onEvent({ type: 'complete', result })
    })

    const user = userEvent.setup()
    renderApp()
    await user.type(screen.getByPlaceholderText('City or country'), 'Shanghai')
    await user.click(screen.getByRole('button', { name: 'Design my journey' }))

    await waitFor(() => {
      expect(screen.getByRole('navigation', { name: 'Trip details' })).toBeInTheDocument()
    })
    expect(screen.queryByRole('button', { name: 'Confirm & finalize' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Agent log' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Shanghai' })).toBeInTheDocument()
    expect(screen.getByLabelText('Plan generated and rule checked deterministically')).toBeInTheDocument()
  })

  it('cancels an active backend plan when the page unmounts', async () => {
    window.scrollTo = vi.fn()
    apiMocks.streamPlan.mockImplementation(() => new Promise(() => {}))
    const user = userEvent.setup()
    const view = renderApp()

    await user.type(screen.getByPlaceholderText('City or country'), 'Shanghai')
    await user.click(screen.getByRole('button', { name: 'Design my journey' }))
    view.unmount()

    await waitFor(() => {
      expect(apiMocks.cancelPlan).toHaveBeenCalledWith(
        expect.any(String),
        { keepalive: true },
      )
    })
  })
})
