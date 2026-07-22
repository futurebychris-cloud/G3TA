import { render, screen } from '@testing-library/react'
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
  it('shows a useful message when speech synthesis is unsupported', () => {
    delete window.speechSynthesis
    delete window.SpeechSynthesisUtterance
    renderSpeechButton()
    expect(screen.getByRole('status')).toHaveTextContent('Read aloud is unavailable')
  })

  it('supports play, pause, resume, and stop through the shared controller', async () => {
    const user = userEvent.setup()
    const cancel = vi.fn()
    const speak = vi.fn((utterance) => utterance.onstart?.())
    const pause = vi.fn()
    const resume = vi.fn()
    window.speechSynthesis = { cancel, speak, pause, resume }
    window.SpeechSynthesisUtterance = class SpeechSynthesisUtterance {
      constructor(text) { this.text = text }
    }
    renderSpeechButton()

    await user.click(screen.getByRole('button', { name: 'Read flight result aloud' }))
    expect(speak).toHaveBeenCalledOnce()
    expect(speak.mock.calls[0][0].text).toContain('John F. Kennedy International Airport (JFK)')
    await user.click(screen.getByRole('button', { name: 'Pause reading flight result' }))
    expect(pause).toHaveBeenCalledOnce()
    await user.click(screen.getByRole('button', { name: 'Resume reading flight result' }))
    expect(resume).toHaveBeenCalledOnce()
    await user.click(screen.getByRole('button', { name: 'Stop reading flight result' }))
    expect(cancel).toHaveBeenCalled()
  })
})
