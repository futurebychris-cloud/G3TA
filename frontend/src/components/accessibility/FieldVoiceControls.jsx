import { useId, useState } from 'react'
import { MdMic, MdVolumeUp } from 'react-icons/md'
import useTextToSpeech from '../../hooks/useTextToSpeech.js'
import useAutoSpeechRecognition from '../../hooks/useAutoSpeechRecognition.js'

const COPY = {
  en: {
    listen: (label) => `Read ${label} and its options aloud`,
    speak: (label) => `Answer ${label} by voice`,
    stopSpeak: 'Stop listening',
  },
  zh: {
    listen: (label) => `朗读${label}及其选项`,
    speak: (label) => `用语音回答${label}`,
    stopSpeak: '停止聆听',
  },
}

function normalizeWords(text) {
  return String(text || '')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
    .split(/\s+/)
    .filter(Boolean)
}

// Forgiving option matching: every word of an option must appear in the spoken
// text, allowing prefix matches so "flights"→flight and "cultural"→culture work.
export function matchOptions(transcript, options) {
  const words = normalizeWords(transcript)
  return options.filter((option) => {
    const optionWords = normalizeWords(option)
    return optionWords.length > 0 && optionWords.every((ow) =>
      words.some((w) => w.startsWith(ow) || (ow.startsWith(w) && w.length >= 3)),
    )
  })
}

/**
 * The universal listen/speak pair for a form field (travelvoice-setup-v2 pattern):
 *  - listen (speaker icon): Piper reads the field title — and every option, for
 *    checkbox groups and dropdowns — out loud.
 *  - speak (mic icon): records for `listenSeconds`, Whisper auto-detects the
 *    language and translates to the site language, then either fills the text
 *    input (onText) or selects the matching choices (options + onMatch).
 * No visible status text — the mic glows while recording; feedback for screen
 * readers stays in an sr-only live region so the buttons never move.
 */
export default function FieldVoiceControls({
  label,
  options,
  readText,
  onMatch,
  onText,
  onSpeakStart,
  language = 'en',
  listenSeconds = 3,
}) {
  const isChinese = language.toLowerCase().startsWith('zh')
  const copy = isChinese ? COPY.zh : COPY.en
  const speechId = useId()
  const speech = useTextToSpeech(speechId, '')
  const [announcement, setAnnouncement] = useState('')
  const [failed, setFailed] = useState(false)

  // Textless failure feedback: the mic flashes red briefly, buttons never move.
  function flashError() {
    setFailed(true)
    window.setTimeout(() => setFailed(false), 2200)
  }

  const recognition = useAutoSpeechRecognition({
    uiLanguage: language,
    translate: true,
    maxListenMs: listenSeconds * 1000,
    onTranscript: (transcript) => {
      if (options && onMatch) {
        const matches = matchOptions(transcript, options)
        setAnnouncement(matches.length ? `Selected: ${matches.join(', ')}` : 'No option recognized.')
        if (!matches.length) flashError()
        onMatch(matches)
      } else if (onText) {
        setAnnouncement(`Heard: ${transcript}`)
        if (onText(transcript) === false) flashError()
      }
    },
  })

  function handleListen() {
    const spoken = readText || (options
      ? (isChinese ? `${label}。选项包括：${options.join('、')}。` : `${label}. Options are: ${options.join(', ')}.`)
      : label)
    speech.playText(spoken, { force: true, userInitiated: true })
  }

  function handleSpeak() {
    if (recognition.isListening) {
      recognition.stop()
      return
    }
    setAnnouncement('')
    onSpeakStart?.()
    recognition.start()
  }

  if (!speech.supported && !recognition.supported) return null

  return (
    <span className="field-voice-controls">
      {speech.supported && (
        <button
          type="button"
          className="va-btn"
          onClick={handleListen}
          disabled={speech.state === 'loading'}
          aria-label={copy.listen(label)}
          title={copy.listen(label)}
        >
          <MdVolumeUp aria-hidden="true" />
        </button>
      )}
      {recognition.supported && (
        <button
          type="button"
          className={`va-btn${recognition.isListening ? ' listening' : ''}${failed ? ' error' : ''}`}
          onClick={handleSpeak}
          aria-label={recognition.isListening ? copy.stopSpeak : copy.speak(label)}
          title={recognition.isListening ? copy.stopSpeak : copy.speak(label)}
        >
          <MdMic aria-hidden="true" />
        </button>
      )}
      <span className="sr-only" role="status" aria-live="polite">
        {announcement || recognition.status}
      </span>
    </span>
  )
}
