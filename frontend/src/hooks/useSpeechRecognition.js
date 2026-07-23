import { useCallback, useEffect, useRef, useState } from 'react'

function recognitionConstructor() {
  if (typeof window === 'undefined') return null
  return window.SpeechRecognition || window.webkitSpeechRecognition || null
}

const MESSAGES = {
  en: {
    unavailable: 'Voice input is unavailable in this browser',
    stopped: 'Voice input stopped',
    listening: 'Listening',
    startError: 'Voice input could not start. You can continue typing.',
    genericError: 'Voice input encountered an error. You can continue typing.',
    errors: {
      'not-allowed': 'Microphone permission was denied. You can continue typing.',
      'service-not-allowed': 'Voice input is blocked by this browser. You can continue typing.',
      'audio-capture': 'No microphone was found. You can continue typing.',
      'no-speech': 'No speech was detected. Try again or continue typing.',
      network: 'Voice recognition could not connect. You can continue typing.',
    },
  },
  zh: {
    unavailable: '此浏览器不支持语音输入',
    stopped: '语音输入已停止',
    listening: '正在聆听',
    startError: '无法启动语音输入，您可以继续打字。',
    genericError: '语音输入出现问题，您可以继续打字。',
    errors: {
      'not-allowed': '麦克风权限被拒绝，您可以继续打字。',
      'service-not-allowed': '此浏览器已阻止语音输入，您可以继续打字。',
      'audio-capture': '未找到麦克风，您可以继续打字。',
      'no-speech': '未检测到语音，请重试或继续打字。',
      network: '语音识别无法连接，您可以继续打字。',
    },
  },
}

export default function useSpeechRecognition({ onTranscript, language } = {}) {
  const recognitionRef = useRef(null)
  const hadErrorRef = useRef(false)
  const [isListening, setIsListening] = useState(false)
  const [status, setStatus] = useState('')
  const supported = Boolean(recognitionConstructor())
  const copy = String(language || '').toLowerCase().startsWith('zh') ? MESSAGES.zh : MESSAGES.en

  const stop = useCallback(() => {
    recognitionRef.current?.stop()
    setIsListening(false)
    setStatus(copy.stopped)
  }, [copy.stopped])

  const start = useCallback(() => {
    const SpeechRecognition = recognitionConstructor()
    if (!SpeechRecognition) {
      setStatus(copy.unavailable)
      return
    }
    recognitionRef.current?.abort()
    hadErrorRef.current = false
    const recognition = new SpeechRecognition()
    recognitionRef.current = recognition
    recognition.lang = language || navigator.language || 'en-US'
    recognition.interimResults = true
    recognition.continuous = false
    recognition.onstart = () => {
      setIsListening(true)
      setStatus(copy.listening)
    }
    recognition.onresult = (event) => {
      let transcript = ''
      let isFinal = true
      for (let index = 0; index < event.results.length; index += 1) {
        transcript += event.results[index][0]?.transcript || ''
        if (event.results[index].isFinal === false) isFinal = false
      }
      if (transcript.trim()) onTranscript?.(transcript.trim(), { isFinal })
    }
    recognition.onerror = (event) => {
      hadErrorRef.current = true
      setIsListening(false)
      setStatus(copy.errors[event.error] || copy.genericError)
    }
    recognition.onend = () => {
      setIsListening(false)
      if (!hadErrorRef.current) setStatus(copy.stopped)
      recognitionRef.current = null
    }
    try {
      recognition.start()
    } catch {
      setStatus(copy.startError)
    }
  }, [copy, language, onTranscript])

  useEffect(() => () => recognitionRef.current?.abort(), [])

  return {
    supported,
    isListening,
    status: supported ? status : copy.unavailable,
    start,
    stop,
  }
}
