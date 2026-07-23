import { useId } from 'react'
import { Languages, Mic, MicOff } from 'lucide-react'
import useAutoSpeechRecognition from '../../hooks/useAutoSpeechRecognition.js'
import useSpeechRecognition from '../../hooks/useSpeechRecognition.js'

export default function VoiceInputButton({
  onTranscript,
  label,
  language = 'en-US',
  showText = false,
  autoDetect = false,
}) {
  const isChinese = language.toLowerCase().startsWith('zh')
  const copy = isChinese
    ? {
        label: '使用语音输入',
        stopLabel: '停止语音输入',
        idleText: '语音回答',
        listeningText: '停止聆听',
        unavailable: '此浏览器不支持语音输入',
      }
    : {
        label: 'Enter destination by voice',
        stopLabel: 'Stop voice input',
        idleText: 'Answer by voice',
        listeningText: 'Stop listening',
        unavailable: 'Voice input is unavailable in this browser',
      }
  const fixedRecognition = useSpeechRecognition({ onTranscript, language })
  const automaticRecognition = useAutoSpeechRecognition({ onTranscript, uiLanguage: language })
  const recognition = autoDetect && automaticRecognition.supported
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
  return (
    <span className="voice-input-control">
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
      <span id={statusId} className={status ? 'speech-status' : 'speech-status sr-only'} role="status" aria-live="polite">
        {status}
      </span>
      {detectedLanguage?.name && (
        <span className="voice-detected-language" role="status" aria-live="polite">
          <Languages size={14} aria-hidden="true" />
          {isChinese ? '已检测' : 'Detected'}: {detectedLanguage.name}
        </span>
      )}
    </span>
  )
}
