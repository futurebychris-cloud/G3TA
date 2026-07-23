import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, vi } from 'vitest'
import App from './App.jsx'
import { parseTripIntake, streamPlan } from './api.js'
import { AccessibilityProvider } from './accessibility/AccessibilityContext.jsx'
import { ACCESSIBILITY_STORAGE_KEY } from './accessibility/AccessibilityContext.jsx'
import { TextToSpeechProvider } from './hooks/useTextToSpeech.js'

vi.mock('./api.js', () => ({
  parseTripIntake: vi.fn(),
  streamPlan: vi.fn(),
  synthesizeSpeech: vi.fn(() => new Promise(() => {})),
}))

const GUIDED_ANSWERS = [
  'New York',
  'Tokyo, Japan',
  'October 10 2026',
  'October 14 2026',
  '4000 US dollars',
  'Japanese',
  'relaxed',
  'flight',
  'quiet hotel',
  'Sensoji',
  'two',
]

function renderApp() {
  localStorage.setItem(ACCESSIBILITY_STORAGE_KEY, JSON.stringify({ onboardingComplete: true }))
  render(
    <AccessibilityProvider>
      <TextToSpeechProvider><App /></TextToSpeechProvider>
    </AccessibilityProvider>,
  )
}

describe('app accessibility entry point', () => {
  beforeEach(() => vi.clearAllMocks())

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
    await user.click(screen.getByRole('button', { name: 'Open guided setup' }))
    expect(await screen.findByRole('dialog', { name: 'Voice-guided Travel Assistant' })).toBeVisible()
    expect(screen.getByRole('heading', { name: /^1\. Where will you be traveling from/ })).toBeVisible()
    // With neither speech synthesis nor a recorder available in jsdom, the
    // voice pair renders nothing — typing remains the fallback.
    expect(screen.queryByRole('button', { name: /Answer .* by voice/ })).not.toBeInTheDocument()
  })

  it('launches the planner when guided answers are complete', async () => {
    const user = userEvent.setup()
    parseTripIntake.mockResolvedValue({
      draft: {
        origin: 'New York',
        location: 'Tokyo, Japan',
        dates: { start: '2026-10-10', end: '2026-10-14' },
        budget: { total: 4000, currency: 'USD' },
        preferences: {
          bites: ['Japanese'],
          transportation_type: ['flight'],
          activity_style: ['relaxed'],
        },
        time_constraints: 'quiet hotel',
        must_go_sites: ['Sensoji'],
        num_people: 2,
      },
      missing: [],
      uncertain: [],
      summary: 'A Tokyo trip for two.',
    })
    streamPlan.mockResolvedValue(undefined)
    renderApp()

    await user.click(screen.getByRole('button', { name: 'Accessibility options' }))
    await user.click(screen.getByRole('button', { name: 'Open guided setup' }))
    for (let index = 0; index < GUIDED_ANSWERS.length; index += 1) {
      const answer = screen.getByRole('textbox', { name: /Your answer/ })
      await user.type(answer, GUIDED_ANSWERS[index])
      if (index < GUIDED_ANSWERS.length - 1) {
        await user.click(screen.getByRole('button', { name: /Next question/ }))
      }
    }
    await user.click(screen.getByRole('button', { name: 'Start planning' }))

    await waitFor(() => expect(streamPlan).toHaveBeenCalledOnce())
    expect(streamPlan.mock.calls[0][0]).toEqual(expect.objectContaining({
      origin: 'New York',
      location: 'Tokyo, Japan',
      dates: { start: '2026-10-10', end: '2026-10-14' },
      budget: { total: 4000, currency: 'USD' },
      num_people: 2,
      is_group: false,
    }))
    expect(screen.queryByRole('dialog', { name: 'Voice-guided Travel Assistant' })).not.toBeInTheDocument()
  })
})
