import { createContext, createElement, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { useAccessibilitySettings } from '../accessibility/AccessibilityContext.jsx'
import { prepareTextForSpeech } from '../utils/accessibility.js'

const TextToSpeechContext = createContext(null)

export function TextToSpeechProvider({ children }) {
  const { settings } = useAccessibilitySettings()
  const [activeId, setActiveId] = useState(null)
  const [speechState, setSpeechState] = useState('idle')
  const supported = typeof window !== 'undefined'
    && 'speechSynthesis' in window
    && typeof window.SpeechSynthesisUtterance === 'function'

  const stop = useCallback(() => {
    if (supported) window.speechSynthesis.cancel()
    setActiveId(null)
    setSpeechState('idle')
  }, [supported])

  const speak = useCallback((id, content) => {
    if (!supported) return
    window.speechSynthesis.cancel()
    const utterance = new window.SpeechSynthesisUtterance(prepareTextForSpeech(content))
    utterance.rate = settings.readingSpeed
    utterance.onstart = () => {
      setActiveId(id)
      setSpeechState('speaking')
    }
    utterance.onend = () => {
      setActiveId(null)
      setSpeechState('idle')
    }
    utterance.onerror = () => {
      setActiveId(null)
      setSpeechState('idle')
    }
    setActiveId(id)
    setSpeechState('speaking')
    window.speechSynthesis.speak(utterance)
  }, [settings.readingSpeed, supported])

  const pause = useCallback(() => {
    if (!supported || speechState !== 'speaking') return
    window.speechSynthesis.pause()
    setSpeechState('paused')
  }, [speechState, supported])

  const resume = useCallback(() => {
    if (!supported || speechState !== 'paused') return
    window.speechSynthesis.resume()
    setSpeechState('speaking')
  }, [speechState, supported])

  useEffect(() => stop, [stop])
  useEffect(() => {
    if (!settings.readAloud) stop()
  }, [settings.readAloud, stop])

  const value = useMemo(() => ({
    supported, activeId, speechState, speak, pause, resume, stop,
  }), [supported, activeId, speechState, speak, pause, resume, stop])

  return createElement(TextToSpeechContext.Provider, { value }, children)
}

export default function useTextToSpeech(id, content) {
  const context = useContext(TextToSpeechContext)
  if (!context) throw new Error('useTextToSpeech must be used inside TextToSpeechProvider')
  const activeIdRef = useRef(context.activeId)
  activeIdRef.current = context.activeId
  useEffect(() => () => {
    if (activeIdRef.current === id) context.stop()
  }, [context.stop, id])
  const isActive = context.activeId === id
  return {
    supported: context.supported,
    state: isActive ? context.speechState : 'idle',
    play: () => context.speak(id, content),
    pause: context.pause,
    resume: context.resume,
    stop: context.stop,
  }
}
