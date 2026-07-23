import { useCallback, useEffect, useRef, useState } from 'react'

function recognitionConstructor() {
  if (typeof window === 'undefined') return null
  return window.SpeechRecognition || window.webkitSpeechRecognition || null
}

const ERROR_MESSAGES = {
  'not-allowed': 'Microphone permission was denied. You can continue typing.',
  'service-not-allowed': 'Voice input is blocked by this browser. You can continue typing.',
  'audio-capture': 'No microphone was found. You can continue typing.',
  'no-speech': 'No speech was detected. Try again or continue typing.',
  network: 'Voice recognition could not connect. You can continue typing.',
}

export default function useSpeechRecognition({ onTranscript, language } = {}) {
  const recognitionRef = useRef(null)
  const hadErrorRef = useRef(false)
  const [isListening, setIsListening] = useState(false)
  const [status, setStatus] = useState('')
  const supported = Boolean(recognitionConstructor())

  const stop = useCallback(() => {
    recognitionRef.current?.stop()
    setIsListening(false)
    setStatus('Voice input stopped')
  }, [])

  const start = useCallback(() => {
    const SpeechRecognition = recognitionConstructor()
    if (!SpeechRecognition) {
      setStatus('Voice input is unavailable in this browser')
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
      setStatus('Listening')
    }
    recognition.onresult = (event) => {
      let transcript = ''
      for (let index = 0; index < event.results.length; index += 1) {
        transcript += event.results[index][0]?.transcript || ''
      }
      if (transcript.trim()) onTranscript?.(transcript.trim())
    }
    recognition.onerror = (event) => {
      hadErrorRef.current = true
      setIsListening(false)
      setStatus(ERROR_MESSAGES[event.error] || 'Voice input encountered an error. You can continue typing.')
    }
    recognition.onend = () => {
      setIsListening(false)
      if (!hadErrorRef.current) setStatus('Voice input stopped')
      recognitionRef.current = null
    }
    try {
      recognition.start()
    } catch {
      setStatus('Voice input could not start. You can continue typing.')
    }
  }, [language, onTranscript])

  useEffect(() => () => recognitionRef.current?.abort(), [])

  return {
    supported,
    isListening,
    status: supported ? status : 'Voice input is unavailable in this browser',
    start,
    stop,
  }
}
