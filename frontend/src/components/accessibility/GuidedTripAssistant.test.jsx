import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, vi } from 'vitest'
import { parseTripIntake, synthesizeSpeech, transcribeSpeech } from '../../api.js'
import { AccessibilityProvider } from '../../accessibility/AccessibilityContext.jsx'
import { TextToSpeechProvider } from '../../hooks/useTextToSpeech.js'
import GuidedTripAssistant from './GuidedTripAssistant.jsx'

vi.mock('../../api.js', () => ({
  parseTripIntake: vi.fn(),
  transcribeSpeech: vi.fn(),
  // Speech playback has its own focused tests. Keep automatic question audio
  // pending here so questionnaire timing cannot race form-navigation assertions.
  synthesizeSpeech: vi.fn(() => new Promise(() => {})),
}))

// The dialog's mic uses the Whisper recording path (MediaRecorder + /speech/transcribe).
function installRecorder() {
  Object.defineProperty(window, 'isSecureContext', { configurable: true, value: true })
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] }) },
  })
  window.MediaRecorder = class MediaRecorder {
    static isTypeSupported = vi.fn(() => true)

    constructor(_stream, options) {
      this.mimeType = options?.mimeType || 'audio/webm'
      this.state = 'inactive'
    }

    start = vi.fn(() => { this.state = 'recording' })

    stop = vi.fn(() => {
      this.state = 'inactive'
      this.ondataavailable?.({ data: new Blob(['spoken audio'], { type: this.mimeType }) })
      this.onstop?.()
    })
  }
}

function removeRecorder() {
  delete window.MediaRecorder
  delete navigator.mediaDevices
  Object.defineProperty(window, 'isSecureContext', { configurable: true, value: false })
}

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

  afterEach(() => {
    removeRecorder()
  })

  it('asks every main-form question and starts planning immediately at the end', async () => {
    const user = userEvent.setup()
    const { onComplete, onClose } = renderAssistant()
    parseTripIntake.mockResolvedValue(RESULT)

    expect(screen.getByRole('heading', { name: /^1\. Where will you be traveling from/ })).toBeVisible()
    expect(screen.getByRole('heading', { name: /Where will you be traveling from/ })).toBeVisible()

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
    installRecorder()
    parseTripIntake.mockResolvedValue(RESULT)
    const { onComplete } = renderAssistant()

    for (let index = 0; index < ANSWERS.length; index += 1) {
      transcribeSpeech.mockResolvedValueOnce({
        text: ANSWERS[index], language: 'en', language_name: 'English', translated: false,
      })
      await user.click(screen.getByRole('button', { name: /Answer .* by voice/ }))
      await user.click(screen.getByRole('button', { name: 'Stop listening' }))
      if (index < ANSWERS.length - 1) {
        // Recognized text stays visible for ~1s before the next question.
        expect(await screen.findByRole('heading', { name: new RegExp(`^${index + 2}\\.`) }, { timeout: 4000 })).toBeVisible()
      }
    }

    await waitFor(() => expect(onComplete).toHaveBeenCalledOnce(), { timeout: 4000 })
    expect(screen.queryByRole('button', { name: /Fill the trip form/ })).not.toBeInTheDocument()
  }, 40000)

  it('switches the visible guide, recognition, and spoken reply language to Chinese', async () => {
    const user = userEvent.setup()
    installRecorder()
    transcribeSpeech.mockReturnValue(new Promise(() => {}))
    renderAssistant()

    await user.click(screen.getByRole('button', { name: '中文' }))

    expect(screen.getByRole('heading', { name: /您将从哪个城市出发/ })).toBeVisible()
    expect(screen.getByRole('button', { name: '中文' })).toHaveAttribute('aria-pressed', 'true')
    await user.click(screen.getByRole('button', { name: '用语音回答出发城市' }))
    expect(await screen.findByText(/正在聆听/)).toBeInTheDocument()
    await waitFor(() => expect(synthesizeSpeech).toHaveBeenCalledWith(
      expect.stringContaining('您将从哪个城市出发'),
      expect.objectContaining({ language: 'zh' }),
    ))
  })
})
