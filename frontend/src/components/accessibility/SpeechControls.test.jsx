import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, vi } from 'vitest'
import { synthesizeSpeech, transcribeSpeech } from '../../api.js'
import { ACCESSIBILITY_STORAGE_KEY, AccessibilityProvider } from '../../accessibility/AccessibilityContext.jsx'
import { TextToSpeechProvider } from '../../hooks/useTextToSpeech.js'
import ReadAloudButton from './ReadAloudButton.jsx'
import VoiceInputButton from './VoiceInputButton.jsx'

vi.mock('../../api.js', () => ({
  synthesizeSpeech: vi.fn(),
  transcribeSpeech: vi.fn(),
}))

let latestAudio
let latestUtterance
let browserSynth

function installPiperAudio() {
  URL.createObjectURL = vi.fn(() => 'blob:piper-audio')
  URL.revokeObjectURL = vi.fn()
  window.Audio = class Audio {
    constructor(src) {
      this.src = src
      latestAudio = this
    }

    play = vi.fn(async () => {
      this.onplay?.()
    })

    pause = vi.fn()
    removeAttribute = vi.fn()
    load = vi.fn()
  }
}

function installBrowserSpeech() {
  window.SpeechSynthesisUtterance = class SpeechSynthesisUtterance {
    constructor(text) {
      this.text = text
      latestUtterance = this
    }
  }
  browserSynth = {
    paused: false,
    speaking: false,
    pending: false,
    getVoices: vi.fn(() => [
      { lang: 'en-US', localService: true, name: 'Local English' },
    ]),
    speak: vi.fn((utterance) => utterance.onstart?.()),
    pause: vi.fn(),
    resume: vi.fn(),
    cancel: vi.fn(),
  }
  Object.defineProperty(window, 'speechSynthesis', {
    configurable: true,
    value: browserSynth,
  })
}

afterEach(() => {
  delete window.speechSynthesis
  delete window.SpeechSynthesisUtterance
})

function renderSpeechButton() {
  localStorage.setItem(ACCESSIBILITY_STORAGE_KEY, JSON.stringify({ readAloud: true }))
  return render(
    <AccessibilityProvider>
      <TextToSpeechProvider>
        <ReadAloudButton id="test-result" text="Flight JFK to NRT at 10:30. USD 500." label="flight result" />
      </TextToSpeechProvider>
    </AccessibilityProvider>,
  )
}

describe('voice input', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows a safe unavailable state when recognition is unsupported', () => {
    delete window.SpeechRecognition
    delete window.webkitSpeechRecognition
    render(<VoiceInputButton onTranscript={() => {}} />)
    expect(screen.getByRole('button', { name: 'Enter destination by voice' })).toBeDisabled()
    expect(screen.getByRole('status')).toHaveTextContent('Voice input is unavailable')
  })

  it('starts, reports listening, inserts recognized text, and stops without submitting', async () => {
    const user = userEvent.setup()
    const onTranscript = vi.fn()
    let recognition
    window.SpeechRecognition = class SpeechRecognition {
      constructor() {
        recognition = this
        this.start = vi.fn(() => this.onstart?.())
        this.stop = vi.fn(() => this.onend?.())
        this.abort = vi.fn()
      }
    }
    render(<VoiceInputButton onTranscript={onTranscript} />)
    await user.click(screen.getByRole('button', { name: 'Enter destination by voice' }))
    expect(screen.getByRole('status')).toHaveTextContent('Listening')
    recognition.onresult({ results: [[{ transcript: 'Shanghai' }]] })
    expect(onTranscript).toHaveBeenCalledWith('Shanghai', { isFinal: true })
    await user.click(screen.getByRole('button', { name: 'Stop voice input' }))
    expect(recognition.stop).toHaveBeenCalledOnce()
    expect(screen.getByRole('status')).toHaveTextContent('Voice input stopped')
  })

  it('records once, auto-detects a common language, and labels the result', async () => {
    const user = userEvent.setup()
    const onTranscript = vi.fn()
    const stopTrack = vi.fn()
    let recorder
    delete window.SpeechRecognition
    delete window.webkitSpeechRecognition
    Object.defineProperty(window, 'isSecureContext', { configurable: true, value: true })
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: stopTrack }] }),
      },
    })
    window.MediaRecorder = class MediaRecorder {
      static isTypeSupported = vi.fn(() => true)

      constructor(_stream, options) {
        recorder = this
        this.mimeType = options?.mimeType || 'audio/webm'
        this.state = 'inactive'
      }

      start = vi.fn(() => {
        this.state = 'recording'
      })

      stop = vi.fn(() => {
        this.state = 'inactive'
        this.ondataavailable?.({ data: new Blob(['spoken audio'], { type: this.mimeType }) })
        this.onstop?.()
      })
    }
    transcribeSpeech.mockResolvedValue({
      text: 'Quiero visitar Madrid',
      language: 'es',
      language_name: 'Spanish',
    })

    render(<VoiceInputButton autoDetect showText onTranscript={onTranscript} />)
    await user.click(screen.getByRole('button', { name: 'Enter destination by voice' }))
    expect(screen.getByText('Listening… speak in any language')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Stop voice input' }))

    await waitFor(() => expect(onTranscript).toHaveBeenCalledWith('Quiero visitar Madrid', {
      isFinal: true,
      language: 'es',
      languageName: 'Spanish',
      translated: false,
    }))
    expect(screen.getByText('Detected: Spanish')).toBeVisible()
    expect(recorder.stop).toHaveBeenCalledOnce()
    expect(stopTrack).toHaveBeenCalledOnce()

    delete window.MediaRecorder
    delete navigator.mediaDevices
    Object.defineProperty(window, 'isSecureContext', { configurable: true, value: false })
  })

  it('prefers browser recognition over Whisper when both are available', async () => {
    const user = userEvent.setup()
    const onTranscript = vi.fn()
    let recognition
    window.SpeechRecognition = class SpeechRecognition {
      constructor() {
        recognition = this
        this.start = vi.fn(() => this.onstart?.())
        this.stop = vi.fn(() => this.onend?.())
        this.abort = vi.fn()
      }
    }
    Object.defineProperty(window, 'isSecureContext', { configurable: true, value: true })
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: vi.fn() },
    })
    window.MediaRecorder = class MediaRecorder {
      static isTypeSupported = vi.fn(() => true)
    }

    render(<VoiceInputButton autoDetect showText language="en-US" onTranscript={onTranscript} />)
    await user.click(screen.getByRole('button', { name: 'Enter destination by voice' }))

    expect(recognition.start).toHaveBeenCalledOnce()
    expect(recognition.lang).toBe('en-US')
    expect(screen.getByRole('status')).toHaveTextContent('Listening')
    expect(transcribeSpeech).not.toHaveBeenCalled()

    delete window.SpeechRecognition
    delete window.MediaRecorder
    delete navigator.mediaDevices
    Object.defineProperty(window, 'isSecureContext', { configurable: true, value: false })
  })

  it('"speak another language" forces Whisper (with translation) even when the browser recognizer is available', async () => {
    const user = userEvent.setup()
    const onTranscript = vi.fn()
    let recognition
    let recorder
    window.SpeechRecognition = class SpeechRecognition {
      constructor() {
        recognition = this
        this.start = vi.fn(() => this.onstart?.())
        this.stop = vi.fn(() => this.onend?.())
        this.abort = vi.fn()
      }
    }
    Object.defineProperty(window, 'isSecureContext', { configurable: true, value: true })
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] }) },
    })
    window.MediaRecorder = class MediaRecorder {
      static isTypeSupported = vi.fn(() => true)

      constructor(_stream, options) {
        recorder = this
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
    transcribeSpeech.mockResolvedValue({
      text: 'I want to visit Madrid',
      language: 'es',
      language_name: 'Spanish',
      translated: true,
    })

    render(<VoiceInputButton autoDetect showText language="en-US" onTranscript={onTranscript} />)
    await user.click(screen.getByRole('button', { name: 'Speak another language' }))
    await user.click(screen.getByRole('button', { name: 'Enter destination by voice' }))
    await user.click(screen.getByRole('button', { name: 'Stop voice input' }))

    expect(recognition).toBeUndefined()
    await waitFor(() => expect(onTranscript).toHaveBeenCalledWith('I want to visit Madrid', {
      isFinal: true,
      language: 'es',
      languageName: 'Spanish',
      translated: true,
    }))
    expect(transcribeSpeech.mock.calls[0][1]).toMatchObject({ translate: true })
    expect(screen.getByText('Detected: Spanish')).toBeVisible()
    expect(screen.getByText(/shown in English/)).toBeVisible()
    expect(recorder.stop).toHaveBeenCalledOnce()

    delete window.SpeechRecognition
    delete window.MediaRecorder
    delete navigator.mediaDevices
    Object.defineProperty(window, 'isSecureContext', { configurable: true, value: false })
  })
})

describe('read aloud', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    installPiperAudio()
    synthesizeSpeech.mockResolvedValue(new Blob([new Uint8Array(64)], { type: 'audio/wav' }))
  })

  it('shows a useful message when audio playback is unsupported', () => {
    delete window.Audio
    renderSpeechButton()
    expect(screen.getByRole('status')).toHaveTextContent('Read aloud is unavailable')
  })

  it('uses Piper and supports play, pause, resume, and stop', async () => {
    const user = userEvent.setup()
    renderSpeechButton()

    await user.click(screen.getByRole('button', { name: 'Read flight result aloud' }))
    await waitFor(() => expect(synthesizeSpeech).toHaveBeenCalledOnce())
    expect(synthesizeSpeech.mock.calls[0][0]).toContain('John F. Kennedy International Airport (JFK)')
    expect(latestAudio.play).toHaveBeenCalledTimes(2)
    await user.click(screen.getByRole('button', { name: 'Pause reading flight result' }))
    expect(latestAudio.pause).toHaveBeenCalledTimes(2)
    await user.click(screen.getByRole('button', { name: 'Resume reading flight result' }))
    expect(latestAudio.play).toHaveBeenCalledTimes(3)
    await user.click(screen.getByRole('button', { name: 'Stop reading flight result' }))
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:piper-audio')
  })

  it('uses the built-in browser voice without calling Piper', async () => {
    const user = userEvent.setup()
    installBrowserSpeech()
    renderSpeechButton()

    await user.click(screen.getByRole('button', { name: 'Read flight result aloud' }))

    expect(browserSynth.speak).toHaveBeenCalledOnce()
    expect(latestUtterance.text).toContain('John F. Kennedy International Airport (JFK)')
    expect(latestUtterance.lang).toBe('en-US')
    expect(synthesizeSpeech).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Pause reading flight result' }))
    expect(browserSynth.pause).toHaveBeenCalledOnce()
    await user.click(screen.getByRole('button', { name: 'Resume reading flight result' }))
    expect(browserSynth.resume).toHaveBeenCalledOnce()
    await user.click(screen.getByRole('button', { name: 'Stop reading flight result' }))
    expect(browserSynth.cancel).toHaveBeenCalledOnce()
  })
})
