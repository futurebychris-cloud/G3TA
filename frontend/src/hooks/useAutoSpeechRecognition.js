import { useCallback, useEffect, useRef, useState } from 'react'
import { transcribeSpeech } from '../api.js'

const MAX_LISTEN_MS = 8000

function recordingSupport() {
  return typeof window !== 'undefined'
    && window.isSecureContext
    && typeof window.MediaRecorder === 'function'
    && Boolean(navigator.mediaDevices?.getUserMedia)
}

function preferredMimeType() {
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/aac']
  return candidates.find((type) => window.MediaRecorder.isTypeSupported?.(type)) || ''
}

export default function useAutoSpeechRecognition({ onTranscript, uiLanguage = 'en', translate = false } = {}) {
  const recorderRef = useRef(null)
  const streamRef = useRef(null)
  const timerRef = useRef(null)
  const requestRef = useRef(null)
  const chunksRef = useRef([])
  const [isListening, setIsListening] = useState(false)
  const [status, setStatus] = useState('')
  const [detectedLanguage, setDetectedLanguage] = useState(null)
  const isChineseUi = String(uiLanguage).toLowerCase().startsWith('zh')
  const targetLanguage = isChineseUi ? 'zh' : 'en'
  const supported = recordingSupport()

  const release = useCallback(() => {
    window.clearTimeout(timerRef.current)
    timerRef.current = null
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    recorderRef.current = null
  }, [])

  const stop = useCallback(() => {
    window.clearTimeout(timerRef.current)
    timerRef.current = null
    const recorder = recorderRef.current
    if (recorder?.state && recorder.state !== 'inactive') recorder.stop()
  }, [])

  const start = useCallback(async () => {
    if (!supported) {
      setStatus(isChineseUi ? '此浏览器不支持自动语言检测' : 'Automatic language detection is unavailable in this browser')
      return
    }
    requestRef.current?.abort()
    setDetectedLanguage(null)
    setStatus(isChineseUi ? '正在连接麦克风…' : 'Connecting to your microphone…')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mimeType = preferredMimeType()
      const recorder = mimeType
        ? new window.MediaRecorder(stream, { mimeType })
        : new window.MediaRecorder(stream)
      streamRef.current = stream
      recorderRef.current = recorder
      chunksRef.current = []
      recorder.ondataavailable = (event) => {
        if (event.data?.size) chunksRef.current.push(event.data)
      }
      recorder.onstop = async () => {
        setIsListening(false)
        setStatus(
          translate
            ? (isChineseUi ? '正在识别语言并翻译成中文…' : 'Detecting language and translating to English…')
            : (isChineseUi ? '正在识别语言和文字…' : 'Detecting language and transcribing…'),
        )
        const audio = new Blob(chunksRef.current, { type: recorder.mimeType || mimeType || 'audio/webm' })
        release()
        const controller = new AbortController()
        requestRef.current = controller
        try {
          const result = await transcribeSpeech(audio, { signal: controller.signal, translate, targetLanguage })
          if (controller.signal.aborted) return
          const detected = {
            code: result.language || '',
            name: result.language_name || result.language || 'Unknown',
            translated: Boolean(result.translated),
          }
          setDetectedLanguage(detected)
          setStatus('')
          onTranscript?.(result.text, {
            isFinal: true,
            language: detected.code,
            languageName: detected.name,
            translated: detected.translated,
          })
        } catch (error) {
          if (!controller.signal.aborted) {
            setStatus(error?.message || (isChineseUi ? '无法识别语音，请重试。' : 'Speech could not be transcribed. Please try again.'))
          }
        } finally {
          if (requestRef.current === controller) requestRef.current = null
        }
      }
      recorder.start()
      setIsListening(true)
      setStatus(
        translate
          ? (isChineseUi ? '正在聆听…可以说任何语言，我们会显示中文' : "Listening… speak any language, we'll show it in English")
          : (isChineseUi ? '正在聆听…说任何语言' : 'Listening… speak in any language'),
      )
      timerRef.current = window.setTimeout(stop, MAX_LISTEN_MS)
    } catch {
      release()
      setIsListening(false)
      setStatus(isChineseUi ? '无法使用麦克风，您可以继续打字。' : 'The microphone is unavailable. You can continue typing.')
    }
  }, [isChineseUi, onTranscript, release, stop, supported, targetLanguage, translate])

  useEffect(() => () => {
    requestRef.current?.abort()
    const recorder = recorderRef.current
    if (recorder) {
      recorder.ondataavailable = null
      recorder.onstop = null
      if (recorder.state && recorder.state !== 'inactive') recorder.stop()
    }
    release()
  }, [release])

  return {
    supported,
    isListening,
    status,
    detectedLanguage,
    start,
    stop,
  }
}
