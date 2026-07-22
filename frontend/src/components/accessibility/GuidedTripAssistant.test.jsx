import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, vi } from 'vitest'
import { parseTripIntake } from '../../api.js'
import { AccessibilityProvider } from '../../accessibility/AccessibilityContext.jsx'
import GuidedTripAssistant from './GuidedTripAssistant.jsx'

vi.mock('../../api.js', () => ({ parseTripIntake: vi.fn() }))

const ANSWERS = [
  'New York',
  'Tokyo',
  'October 10 2026',
  'October 14 2026',
  '4000 US dollars',
  'Japanese',
  'relaxed',
  'flight',
  'quiet hotel',
  'none',
  'two',
]

const RESULT = {
  draft: {
    origin: 'New York',
    location: 'Tokyo',
    dates: { start: '2026-10-10', end: '2026-10-14' },
    budget: { total: 4000, currency: 'USD' },
    preferences: {
      bites: ['Japanese'],
      transportation_type: ['flight'],
      activity_style: ['relaxed'],
    },
    time_constraints: 'quiet hotel',
    must_go_sites: [],
    num_people: 2,
  },
  missing: [],
  uncertain: ['time_constraints'],
  summary: 'A Tokyo trip for two with a USD 4,000 budget.',
}

function renderAssistant(onApplyDraft = vi.fn()) {
  render(
    <AccessibilityProvider>
      <GuidedTripAssistant
        open
        onClose={vi.fn()}
        onApplyDraft={onApplyDraft}
      />
    </AccessibilityProvider>,
  )
  return onApplyDraft
}

async function answerEveryQuestion(user) {
  for (let index = 0; index < ANSWERS.length; index += 1) {
    const answer = screen.getByRole('textbox', { name: /Your answer/ })
    await user.clear(answer)
    await user.type(answer, ANSWERS[index])
    if (index < ANSWERS.length - 1) {
      await user.click(screen.getByRole('button', { name: /Next question/ }))
    }
  }
}

describe('voice-guided trip accessibility add-on', () => {
  beforeEach(() => vi.clearAllMocks())

  it('asks every main-form question, creates a review, and never submits directly', async () => {
    const user = userEvent.setup()
    const onApplyDraft = renderAssistant()
    parseTripIntake.mockResolvedValue(RESULT)

    expect(screen.getByText('Question 1 of 11')).toBeVisible()
    expect(screen.getByRole('heading', { name: /What city are you leaving from/ })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Answer flying from by voice' })).toBeInTheDocument()

    await answerEveryQuestion(user)
    await user.click(screen.getByRole('button', { name: /Review my answers/ }))

    expect(await screen.findByText('Your answers are ready')).toBeVisible()
    expect(screen.getByText('A Tokyo trip for two with a USD 4,000 budget.')).toBeVisible()
    expect(screen.getByRole('note')).toHaveTextContent('Please double-check: Anything we should work around?')
    expect(onApplyDraft).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: /Fill the trip form/ }))
    expect(onApplyDraft).toHaveBeenCalledWith(RESULT.draft, {
      summary: RESULT.summary,
      missing: [],
      uncertain: ['time_constraints'],
    })
  })

  it('keeps missing details inside guided setup and asks only that question again', async () => {
    const user = userEvent.setup()
    parseTripIntake
      .mockResolvedValueOnce({
        ...RESULT,
        draft: { ...RESULT.draft, budget: { total: 4000, currency: null } },
        missing: ['currency'],
        uncertain: [],
      })
      .mockResolvedValueOnce(RESULT)
    renderAssistant()

    await answerEveryQuestion(user)
    await user.click(screen.getByRole('button', { name: /Review my answers/ }))

    expect(await screen.findByRole('heading', { name: /What is your total budget/ })).toBeVisible()
    expect(screen.getByRole('alert')).toHaveTextContent('stay in guided setup')
    const answer = screen.getByRole('textbox', { name: /Your answer/ })
    await user.clear(answer)
    await user.type(answer, 'four thousand US dollars')
    await user.click(screen.getByRole('button', { name: /Review my answers/ }))

    expect(await screen.findByText('Your answers are ready')).toBeVisible()
    expect(parseTripIntake).toHaveBeenCalledTimes(2)
  })
})
