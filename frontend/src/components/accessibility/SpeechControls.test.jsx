import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, vi } from 'vitest'
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
    }))
    expect(screen.getByText('Detected: Spanish')).toBeVisible()
    expect(recorder.stop).toHaveBeenCalledOnce()
    expect(stopTrack).toHaveBeenCalledOnce()

    delete window.MediaRecorder
    delete navigator.mediaDevices
    Object.defineProperty(window, 'isSecureContext', { configurable: true, value: false })
  })
})

describe('read aloud', () => {
  beforeEach(() => {
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
})
