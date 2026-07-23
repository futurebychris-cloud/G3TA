import { useId } from 'react'
import { Mic, MicOff } from 'lucide-react'
import useSpeechRecognition from '../../hooks/useSpeechRecognition.js'

export default function VoiceInputButton({ onTranscript, label = 'Enter destination by voice', showText = false }) {
  const { supported, isListening, status, start, stop } = useSpeechRecognition({ onTranscript })
  const statusId = useId()
  return (
    <span className="voice-input-control">
      <button
        className={`${isListening ? 'voice-button listening' : 'voice-button'}${showText ? ' voice-button-wide' : ''}`}
        type="button"
        onClick={isListening ? stop : start}
        disabled={!supported}
        aria-label={isListening ? 'Stop voice input' : label}
        aria-pressed={isListening}
        aria-describedby={statusId}
        title={supported ? label : 'Voice input is unavailable in this browser'}
      >
        {isListening ? <MicOff size={18} aria-hidden="true" /> : <Mic size={18} aria-hidden="true" />}
        {showText && <span>{isListening ? 'Stop listening' : 'Answer by voice'}</span>}
      </button>
      <span id={statusId} className={status ? 'speech-status' : 'speech-status sr-only'} role="status" aria-live="polite">
        {status}
      </span>
    </span>
  )
}
