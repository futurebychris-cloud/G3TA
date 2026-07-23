import { useId, useState } from 'react'
import { Mic, MicOff, Volume2 } from 'lucide-react'
import useTextToSpeech from '../../hooks/useTextToSpeech.js'
import useAutoSpeechRecognition from '../../hooks/useAutoSpeechRecognition.js'

const COPY = {
  en: {
    listen: (label) => `Listen to ${label} options`,
    speak: (label) => `Answer ${label} by voice`,
    stopSpeak: 'Stop listening',
    matched: (values) => `Selected: ${values.join(', ')}`,
    noMatch: "Didn't catch an option in that — try again, naming one of the choices.",
  },
  zh: {
    listen: (label) => `朗读${label}选项`,
    speak: (label) => `用语音回答${label}`,
    stopSpeak: '停止聆听',
    matched: (values) => `已选择：${values.join('、')}`,
    noMatch: '没有识别到选项，请重试并说出其中一个选项。',
  },
}

function matchOptions(transcript, options) {
  const normalized = String(transcript || '').toLowerCase()
  return options.filter((option) => normalized.includes(String(option).toLowerCase()))
}

/**
 * Pairs a "listen" (Piper reads the field title + every option aloud) and a
 * "speak" (Whisper records for a few seconds, auto-detects the language,
 * translates to the site's current language, then matches spoken words
 * against the option list) control for any choice-based form field —
 * checkbox groups today, the same pattern extends to native <select>s.
 */
export default function FieldVoiceControls({
  label,
  options,
  language = 'en',
  onMatch,
  maxListenSeconds = 3,
}) {
  const isChinese = language.toLowerCase().startsWith('zh')
  const copy = isChinese ? COPY.zh : COPY.en
  const speechId = useId()
  const speech = useTextToSpeech(speechId, '')
  const [confirmation, setConfirmation] = useState('')
  const recognition = useAutoSpeechRecognition({
    uiLanguage: language,
    translate: true,
    maxListenMs: maxListenSeconds * 1000,
    onTranscript: (transcript) => {
      const matches = matchOptions(transcript, options)
      setConfirmation(matches.length ? copy.matched(matches) : copy.noMatch)
      if (matches.length) onMatch(matches)
    },
  })

  function handleListen() {
    setConfirmation('')
    const spoken = isChinese
      ? `${label}。选项包括：${options.join('、')}。`
      : `${label}. Options are: ${options.join(', ')}.`
    speech.playText(spoken, { force: true, userInitiated: true })
  }

  function handleSpeak() {
    if (recognition.isListening) {
      recognition.stop()
      return
    }
    setConfirmation('')
    recognition.start()
  }

  if (!speech.supported && !recognition.supported) return null

  return (
    <span className="field-voice-controls">
      {speech.supported && (
        <button
          type="button"
          className="field-voice-btn field-voice-listen"
          onClick={handleListen}
          disabled={speech.state === 'loading'}
          aria-label={copy.listen(label)}
          title={copy.listen(label)}
        >
          <Volume2 size={15} aria-hidden="true" />
        </button>
      )}
      {recognition.supported && (
        <button
          type="button"
          className={recognition.isListening ? 'field-voice-btn field-voice-speak listening' : 'field-voice-btn field-voice-speak'}
          onClick={handleSpeak}
          aria-label={recognition.isListening ? copy.stopSpeak : copy.speak(label)}
          title={recognition.isListening ? copy.stopSpeak : copy.speak(label)}
        >
          {recognition.isListening ? <MicOff size={15} aria-hidden="true" /> : <Mic size={15} aria-hidden="true" />}
        </button>
      )}
      <span className={confirmation || recognition.status ? 'field-voice-status' : 'field-voice-status sr-only'} role="status" aria-live="polite">
        {confirmation || recognition.status}
      </span>
    </span>
  )
}
