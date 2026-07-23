import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, vi } from 'vitest'
import { parseTripIntake, synthesizeSpeech } from '../../api.js'
import { AccessibilityProvider } from '../../accessibility/AccessibilityContext.jsx'
import { TextToSpeechProvider } from '../../hooks/useTextToSpeech.js'
import GuidedTripAssistant from './GuidedTripAssistant.jsx'

vi.mock('../../api.js', () => ({
  parseTripIntake: vi.fn(),
  // Speech playback has its own focused tests. Keep automatic question audio
  // pending here so questionnaire timing cannot race form-navigation assertions.
  synthesizeSpeech: vi.fn(() => new Promise(() => {})),
}))

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

function renderAssistant(onComplete = vi.fn(), onClose = vi.fn()) {
  render(
    <AccessibilityProvider>
      <TextToSpeechProvider>
        <GuidedTripAssistant
          open
          onClose={onClose}
          onComplete={onComplete}
        />
      </TextToSpeechProvider>
    </AccessibilityProvider>,
  )
  return { onComplete, onClose }
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
  beforeEach(() => {
    vi.clearAllMocks()
    delete window.SpeechRecognition
    delete window.webkitSpeechRecognition
  })

  it('asks every main-form question and starts planning immediately at the end', async () => {
    const user = userEvent.setup()
    const { onComplete, onClose } = renderAssistant()
    parseTripIntake.mockResolvedValue(RESULT)

    expect(screen.getByText('Question 1 of 11')).toBeVisible()
    expect(screen.getByRole('heading', { name: /Where will you be traveling from/ })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Answer flying from by voice' })).toBeInTheDocument()

    await answerEveryQuestion(user)
    await user.click(screen.getByRole('button', { name: /Start planning/ }))

    await waitFor(() => expect(onComplete).toHaveBeenCalledWith(RESULT.draft, {
      summary: RESULT.summary,
      missing: [],
      uncertain: ['time_constraints'],
    }))
    expect(onClose).toHaveBeenCalledOnce()
    expect(screen.queryByRole('button', { name: /Fill the trip form/ })).not.toBeInTheDocument()
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
    await user.click(screen.getByRole('button', { name: /Start planning/ }))

    expect(await screen.findByRole('heading', { name: /What budget would you like us to plan around/ })).toBeVisible()
    expect(screen.getByRole('alert')).toHaveTextContent('stay in guided setup')
    const answer = screen.getByRole('textbox', { name: /Your answer/ })
    await user.clear(answer)
    await user.type(answer, 'four thousand US dollars')
    await user.click(screen.getByRole('button', { name: /Start planning/ }))

    await waitFor(() => expect(parseTripIntake).toHaveBeenCalledTimes(2))
  })

  it('advances final voice answers and starts without a finish-form click', async () => {
    const user = userEvent.setup()
    let recognition
    window.SpeechRecognition = class SpeechRecognition {
      constructor() {
        recognition = this
        this.start = vi.fn(() => this.onstart?.())
        this.stop = vi.fn(() => this.onend?.())
        this.abort = vi.fn()
      }
    }
    parseTripIntake.mockResolvedValue(RESULT)
    const { onComplete } = renderAssistant()

    for (let index = 0; index < ANSWERS.length; index += 1) {
      await user.click(screen.getByRole('button', { name: /Answer .* by voice/ }))
      const finalResult = [[{ transcript: ANSWERS[index] }]]
      finalResult[0].isFinal = true
      await act(async () => {
        recognition.onresult({ results: finalResult })
        recognition.onend()
      })
      if (index < ANSWERS.length - 1) {
        expect(await screen.findByText(`Question ${index + 2} of 11`)).toBeVisible()
      }
    }

    await waitFor(() => expect(onComplete).toHaveBeenCalledOnce())
    expect(screen.queryByRole('button', { name: /Fill the trip form/ })).not.toBeInTheDocument()
  })

  it('switches the visible guide, recognition, and spoken reply language to Chinese', async () => {
    const user = userEvent.setup()
    let recognition
    window.SpeechRecognition = class SpeechRecognition {
      constructor() {
        recognition = this
        this.start = vi.fn(() => this.onstart?.())
        this.stop = vi.fn(() => this.onend?.())
        this.abort = vi.fn()
      }
    }
    renderAssistant()

    await user.click(screen.getByRole('button', { name: '中文' }))

    expect(screen.getByRole('heading', { name: '您将从哪个城市出发？' })).toBeVisible()
    expect(screen.getByRole('button', { name: '中文' })).toHaveAttribute('aria-pressed', 'true')
    await user.click(screen.getByRole('button', { name: '用语音回答出发城市' }))
    expect(recognition.lang).toBe('zh-CN')
    expect(screen.getByText('正在聆听')).toBeInTheDocument()
    await waitFor(() => expect(synthesizeSpeech).toHaveBeenCalledWith(
      expect.stringContaining('您将从哪个城市出发'),
      expect.objectContaining({ language: 'zh' }),
    ))
  })
})
