import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { AccessibilityProvider } from '../accessibility/AccessibilityContext.jsx'
import { TextToSpeechProvider } from '../hooks/useTextToSpeech.js'
import { parseTripDescription } from '../api.js'
import GuidedTripAssistant from './GuidedTripAssistant.jsx'

vi.mock('../api.js', () => ({
  parseTripDescription: vi.fn(),
  synthesizeSpeech: vi.fn(),
}))

describe('guided trip setup', () => {
  it('turns a spoken-or-typed description into a reviewable form draft', async () => {
    const user = userEvent.setup()
    const onApply = vi.fn()
    parseTripDescription.mockResolvedValue({
      summary: 'Hangzhou to Shanghai for two travelers.',
      missing: [],
      uncertain: ['budget_total'],
      draft: {
        origin: 'Hangzhou',
        location: 'Shanghai',
        dates: { start: '2026-08-01', end: '2026-08-03' },
        budget: { total: 6000, currency: 'CNY' },
        preferences: { bites: ['Chinese'], transportation_type: ['train'], activity_style: ['cultural'] },
        must_go_sites: ['The Bund'],
        num_people: 2,
      },
    })

    render(
      <AccessibilityProvider>
        <TextToSpeechProvider>
          <GuidedTripAssistant onApply={onApply} />
        </TextToSpeechProvider>
      </AccessibilityProvider>,
    )

    await user.click(screen.getByRole('button', { name: /Describe or speak your trip instead/ }))
    await user.type(
      screen.getByRole('textbox', { name: 'Trip description' }),
      'Two travelers from Hangzhou to Shanghai in August with a CNY 6000 budget.',
    )
    await user.click(screen.getByRole('button', { name: 'Build draft' }))

    expect(await screen.findByText('Hangzhou to Shanghai for two travelers.')).toBeVisible()
    expect(screen.getByText(/Please double-check: budget_total/)).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Apply draft to form' }))
    expect(onApply).toHaveBeenCalledWith(expect.objectContaining({
      location: 'Shanghai',
      num_people: 2,
    }))
  })
})
