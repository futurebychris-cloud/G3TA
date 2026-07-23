import { useId, useState } from 'react'
import { Globe, Languages, Mic, MicOff } from 'lucide-react'
import useAutoSpeechRecognition from '../../hooks/useAutoSpeechRecognition.js'
import useSpeechRecognition from '../../hooks/useSpeechRecognition.js'

const COPY = {
  en: {
    label: 'Enter destination by voice',
    stopLabel: 'Stop voice input',
    idleText: 'Answer by voice',
    listeningText: 'Stop listening',
    unavailable: 'Voice input is unavailable in this browser',
    detected: 'Detected',
    translatedNote: 'shown in English',
    anyLanguageOn: 'Any language: on',
    anyLanguageOff: 'Speak another language',
    anyLanguageHint: 'Answer in Spanish, Russian, or any language — we detect it and show English text.',
  },
  zh: {
    label: '使用语音输入',
    stopLabel: '停止语音输入',
    idleText: '语音回答',
    listeningText: '停止聆听',
    unavailable: '此浏览器不支持语音输入',
    detected: '已检测',
    translatedNote: '已翻译为中文',
    anyLanguageOn: '任何语言：开',
    anyLanguageOff: '说其他语言',
    anyLanguageHint: '可以用西班牙语、俄语或任何语言回答——我们会识别语言并显示中文文字。',
  },
}

export default function VoiceInputButton({
  onTranscript,
  label,
  language = 'en-US',
  showText = false,
  autoDetect = false,
}) {
  const isChinese = language.toLowerCase().startsWith('zh')
  const copy = isChinese ? COPY.zh : COPY.en
  const [anyLanguageMode, setAnyLanguageMode] = useState(false)

  const fixedRecognition = useSpeechRecognition({ onTranscript, language })
  const automaticRecognition = useAutoSpeechRecognition({
    onTranscript,
    uiLanguage: language,
    translate: anyLanguageMode,
  })
  // "Speak another language" always uses Whisper (the only path that can auto-detect
  // and translate). Otherwise prefer the browser recognizer — it works without the
  // optional Docker/Whisper service — falling back to Whisper only when the browser
  // has no built-in recognizer at all.
  const recognition = anyLanguageMode && automaticRecognition.supported
    ? automaticRecognition
    : fixedRecognition.supported
      ? fixedRecognition
      : autoDetect && automaticRecognition.supported
        ? automaticRecognition
        : fixedRecognition
  const {
    supported,
    isListening,
    status,
    detectedLanguage,
    start,
    stop,
  } = recognition
  const statusId = useId()
  const canOfferAnyLanguage = showText && automaticRecognition.supported
  // The backend already only sets `translated` when the spoken language differed
  // from the current UI's target language (English or Chinese), so trust it as-is.
  const showTranslatedNote = anyLanguageMode && detectedLanguage?.translated

  return (
    <div className="voice-input-control">
      <div className="voice-input-row">
        <button
          className={`${isListening ? 'voice-button listening' : 'voice-button'}${showText ? ' voice-button-wide' : ''}`}
          type="button"
          onClick={isListening ? stop : start}
          disabled={!supported}
          aria-label={isListening ? copy.stopLabel : (label || copy.label)}
          aria-pressed={isListening}
          aria-describedby={statusId}
          title={supported ? (label || copy.label) : copy.unavailable}
        >
          {isListening ? <MicOff size={18} aria-hidden="true" /> : <Mic size={18} aria-hidden="true" />}
          {showText && <span>{isListening ? copy.listeningText : copy.idleText}</span>}
        </button>

        {canOfferAnyLanguage && (
          <button
            type="button"
            className={anyLanguageMode ? 'voice-any-language active' : 'voice-any-language'}
            onClick={() => setAnyLanguageMode((current) => !current)}
            disabled={isListening}
            aria-pressed={anyLanguageMode}
            title={copy.anyLanguageHint}
          >
            <Globe size={13} aria-hidden="true" />
            {anyLanguageMode ? copy.anyLanguageOn : copy.anyLanguageOff}
          </button>
        )}
      </div>

      {showText && anyLanguageMode && (
        <p className="voice-any-language-hint">{copy.anyLanguageHint}</p>
      )}

      <div className="voice-input-feedback">
        <span id={statusId} className={status ? 'speech-status' : 'speech-status sr-only'} role="status" aria-live="polite">
          {status}
        </span>
        {detectedLanguage?.name && (
          <span className="voice-detected-language" role="status" aria-live="polite">
            <Languages size={13} aria-hidden="true" />
            {copy.detected}: {detectedLanguage.name}
            {showTranslatedNote && <em>&nbsp;→&nbsp;{copy.translatedNote}</em>}
          </span>
        )}
      </div>
    </div>
  )
}
