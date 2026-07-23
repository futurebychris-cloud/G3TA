import { Pause, Play, Square, Volume2 } from 'lucide-react'
import { useAccessibilitySettings } from '../../accessibility/AccessibilityContext.jsx'
import useTextToSpeech from '../../hooks/useTextToSpeech.js'

export default function ReadAloudButton({ id, text, label = 'this content' }) {
  const { settings } = useAccessibilitySettings()
  const speech = useTextToSpeech(id, text)
  if (!settings.readAloud) return null
  if (!speech.supported) {
    return <span className="speech-unavailable" role="status">Read aloud is unavailable in this browser.</span>
  }

  const primaryAction = speech.state === 'speaking' ? speech.pause : speech.state === 'paused' ? speech.resume : speech.play
  const primaryLabel = speech.state === 'speaking'
    ? `Pause reading ${label}`
    : speech.state === 'paused'
      ? `Resume reading ${label}`
      : speech.state === 'loading'
        ? `Preparing Piper voice for ${label}`
      : `Read ${label} aloud`

  return (
    <span className="read-aloud-controls">
      <button
        type="button"
        className={speech.state !== 'idle' ? 'read-aloud-button active' : 'read-aloud-button'}
        onClick={primaryAction}
        disabled={speech.state === 'loading'}
        aria-label={primaryLabel}
        title={primaryLabel}
      >
        {speech.state === 'speaking' ? <Pause size={16} aria-hidden="true" />
          : speech.state === 'paused' ? <Play size={16} aria-hidden="true" />
            : <Volume2 size={16} aria-hidden="true" />}
        <span>{speech.state === 'speaking' ? 'Pause' : speech.state === 'paused' ? 'Resume' : speech.state === 'loading' ? 'Preparing…' : 'Read aloud'}</span>
      </button>
      {speech.state !== 'idle' && (
        <button type="button" className="stop-reading-button" onClick={speech.stop} aria-label={`Stop reading ${label}`}>
          <Square size={13} aria-hidden="true" /> Stop
        </button>
      )}
      <span className="sr-only" role="status" aria-live="polite">
        {speech.state === 'loading'
          ? `Preparing Piper voice for ${label}`
          : speech.state === 'speaking'
            ? `Reading ${label} with Piper`
            : speech.state === 'paused'
              ? `Reading ${label} paused`
              : speech.error}
      </span>
    </span>
  )
}
