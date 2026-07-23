import { createContext, createElement, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { useAccessibilitySettings } from '../accessibility/AccessibilityContext.jsx'
import { synthesizeSpeech } from '../api.js'
import { prepareTextForSpeech } from '../utils/accessibility.js'

const TextToSpeechContext = createContext(null)

function speechLanguage() {
  const pageLanguage = typeof document !== 'undefined' ? document.documentElement.lang : ''
  const browserLanguage = typeof navigator !== 'undefined' ? navigator.language : ''
  return String(pageLanguage || browserLanguage || 'en').toLowerCase().startsWith('zh') ? 'zh' : 'en'
}

export function TextToSpeechProvider({ children }) {
  const { settings } = useAccessibilitySettings()
  const [activeId, setActiveId] = useState(null)
  const [speechState, setSpeechState] = useState('idle')
  const [speechError, setSpeechError] = useState('')
  const audioRef = useRef(null)
  const audioUrlRef = useRef('')
  const requestRef = useRef(null)
  const requestVersionRef = useRef(0)
  const requiresReadAloudRef = useRef(false)
  const supported = typeof window !== 'undefined'
    && typeof window.Audio === 'function'
    && typeof URL !== 'undefined'
    && typeof URL.createObjectURL === 'function'
    && typeof URL.revokeObjectURL === 'function'

  const releaseAudio = useCallback(() => {
    const audio = audioRef.current
    if (audio) {
      audio.onplay = null
      audio.onended = null
      audio.onerror = null
      audio.pause()
      audio.removeAttribute?.('src')
      audio.load?.()
    }
    audioRef.current = null
    if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current)
    audioUrlRef.current = ''
  }, [])

  const stop = useCallback(() => {
    requestVersionRef.current += 1
    requestRef.current?.abort()
    requestRef.current = null
    releaseAudio()
    setActiveId(null)
    setSpeechState('idle')
    setSpeechError('')
    requiresReadAloudRef.current = false
  }, [releaseAudio])

  const speak = useCallback(async (id, content, { force = false } = {}) => {
    if (!supported || (!force && !settings.readAloud)) return
    const preparedText = prepareTextForSpeech(content)
    if (!preparedText) return

    stop()
    const requestVersion = requestVersionRef.current
    const controller = new AbortController()
    requestRef.current = controller
    requiresReadAloudRef.current = !force
    setActiveId(id)
    setSpeechState('loading')
    setSpeechError('')

    try {
      const blob = await synthesizeSpeech(preparedText, {
        language: speechLanguage(),
        speed: settings.readingSpeed,
        signal: controller.signal,
      })
      if (controller.signal.aborted || requestVersion !== requestVersionRef.current) return

      const audioUrl = URL.createObjectURL(blob)
      const audio = new window.Audio(audioUrl)
      audio.preload = 'auto'
      audioUrlRef.current = audioUrl
      audioRef.current = audio
      audio.onplay = () => {
        setActiveId(id)
        setSpeechState('speaking')
      }
      audio.onended = () => {
        releaseAudio()
        setActiveId(null)
        setSpeechState('idle')
        requiresReadAloudRef.current = false
      }
      audio.onerror = () => {
        releaseAudio()
        setActiveId(id)
        setSpeechState('error')
        setSpeechError('Piper audio could not be played.')
      }
      await audio.play()
    } catch (error) {
      if (controller.signal.aborted || requestVersion !== requestVersionRef.current) return
      releaseAudio()
      setActiveId(id)
      setSpeechState('error')
      setSpeechError(error?.message || 'Piper voice is unavailable.')
    } finally {
      if (requestRef.current === controller) requestRef.current = null
    }
  }, [releaseAudio, settings.readAloud, settings.readingSpeed, stop, supported])

  const pause = useCallback(() => {
    if (speechState !== 'speaking' || !audioRef.current) return
    audioRef.current.pause()
    setSpeechState('paused')
  }, [speechState])

  const resume = useCallback(async () => {
    if (speechState !== 'paused' || !audioRef.current) return
    try {
      await audioRef.current.play()
      setSpeechState('speaking')
    } catch {
      setSpeechState('error')
      setSpeechError('Piper audio could not resume.')
    }
  }, [speechState])

  useEffect(() => stop, [stop])
  useEffect(() => {
    if (!settings.readAloud && requiresReadAloudRef.current) stop()
  }, [settings.readAloud, stop])

  const value = useMemo(() => ({
    supported,
    activeId,
    speechState,
    speechError,
    speak,
    pause,
    resume,
    stop,
  }), [supported, activeId, speechState, speechError, speak, pause, resume, stop])

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
  const play = useCallback(
    () => context.speak(id, content),
    [content, context.speak, id],
  )
  const playText = useCallback(
    (nextContent, options) => context.speak(id, nextContent, options),
    [context.speak, id],
  )
  return {
    supported: context.supported,
    state: isActive ? context.speechState : 'idle',
    error: isActive ? context.speechError : '',
    play,
    playText,
    pause: context.pause,
    resume: context.resume,
    stop: context.stop,
  }
}
