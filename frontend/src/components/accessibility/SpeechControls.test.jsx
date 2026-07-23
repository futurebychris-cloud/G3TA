import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { ACCESSIBILITY_STORAGE_KEY, AccessibilityProvider } from '../../accessibility/AccessibilityContext.jsx'
import { TextToSpeechProvider } from '../../hooks/useTextToSpeech.js'
import ReadAloudButton from './ReadAloudButton.jsx'
import VoiceInputButton from './VoiceInputButton.jsx'

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
    expect(onTranscript).toHaveBeenCalledWith('Shanghai')
    await user.click(screen.getByRole('button', { name: 'Stop voice input' }))
    expect(recognition.stop).toHaveBeenCalledOnce()
    expect(screen.getByRole('status')).toHaveTextContent('Voice input stopped')
  })
})

describe('read aloud', () => {
  it('shows a useful message when Piper audio playback is unsupported', () => {
    delete window.Audio
    renderSpeechButton()
    expect(screen.getByRole('status')).toHaveTextContent('Piper read aloud is unavailable')
  })

  it('requests Piper audio and supports play, pause, resume, and stop', async () => {
    const user = userEvent.setup()
    const pause = vi.fn()
    const play = vi.fn().mockResolvedValue(undefined)
    const audio = { play, pause, currentTime: 0, onended: null, onerror: null }
    window.Audio = vi.fn(function Audio() { return audio })
    window.fetch = vi.fn().mockResolvedValue({
      ok: true,
      blob: vi.fn().mockResolvedValue(new Blob(['wav'], { type: 'audio/wav' })),
    })
    window.URL.createObjectURL = vi.fn(() => 'blob:piper-test')
    window.URL.revokeObjectURL = vi.fn()
    renderSpeechButton()

    await user.click(screen.getByRole('button', { name: 'Read flight result aloud' }))
    await waitFor(() => expect(play).toHaveBeenCalledOnce())
    const request = JSON.parse(window.fetch.mock.calls[0][1].body)
    expect(request.text).toContain('John F. Kennedy International Airport (JFK)')
    expect(request.speed).toBe(1)
    await user.click(screen.getByRole('button', { name: 'Pause reading flight result' }))
    expect(pause).toHaveBeenCalledOnce()
    await user.click(screen.getByRole('button', { name: 'Resume reading flight result' }))
    expect(play).toHaveBeenCalledTimes(2)
    await user.click(screen.getByRole('button', { name: 'Stop reading flight result' }))
    expect(pause).toHaveBeenCalledTimes(2)
    expect(window.URL.revokeObjectURL).toHaveBeenCalledWith('blob:piper-test')
  })
})
