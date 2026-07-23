import { createContext, createElement, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { useAccessibilitySettings } from '../accessibility/AccessibilityContext.jsx'
import { synthesizeSpeech } from '../api.js'
import { prepareTextForSpeech } from '../utils/accessibility.js'

const TextToSpeechContext = createContext(null)

export function TextToSpeechProvider({ children }) {
  const { settings } = useAccessibilitySettings()
  const [activeId, setActiveId] = useState(null)
  const [speechState, setSpeechState] = useState('idle')
  const [speechError, setSpeechError] = useState('')
  const audioRef = useRef(null)
  const urlRef = useRef('')
  const abortRef = useRef(null)
  const requestTokenRef = useRef(0)

  const supported = typeof window !== 'undefined'
    && typeof window.Audio === 'function'
    && typeof window.fetch === 'function'
    && typeof window.URL?.createObjectURL === 'function'

  const release = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    const audio = audioRef.current
    if (audio) {
      audio.pause()
      audio.onended = null
      audio.onerror = null
      try { audio.currentTime = 0 } catch { /* Some browsers expose a read-only value before metadata. */ }
    }
    audioRef.current = null
    if (urlRef.current) {
      window.URL.revokeObjectURL(urlRef.current)
      urlRef.current = ''
    }
  }, [])

  const stop = useCallback(() => {
    requestTokenRef.current += 1
    release()
    setActiveId(null)
    setSpeechState('idle')
    setSpeechError('')
  }, [release])

  const speak = useCallback(async (id, content) => {
    if (!supported) return
    stop()
    const requestToken = requestTokenRef.current
    const controller = new AbortController()
    abortRef.current = controller
    setActiveId(id)
    setSpeechState('loading')
    setSpeechError('')
    try {
      const text = prepareTextForSpeech(content)
      const blob = await synthesizeSpeech(text, settings.readingSpeed, {
        signal: controller.signal,
      })
      if (requestToken !== requestTokenRef.current) return
      const url = window.URL.createObjectURL(blob)
      urlRef.current = url
      const audio = new window.Audio(url)
      audioRef.current = audio
      audio.onended = () => {
        if (requestToken !== requestTokenRef.current) return
        release()
        setActiveId(null)
        setSpeechState('idle')
      }
      audio.onerror = () => {
        if (requestToken !== requestTokenRef.current) return
        release()
        setActiveId(null)
        setSpeechState('error')
        setSpeechError('Piper returned audio that this browser could not play.')
      }
      await audio.play()
      if (requestToken !== requestTokenRef.current) return
      setSpeechState('speaking')
    } catch (error) {
      if (error?.name === 'AbortError' || requestToken !== requestTokenRef.current) return
      release()
      setActiveId(null)
      setSpeechState('error')
      setSpeechError(error?.message || 'Piper read aloud is unavailable.')
    }
  }, [release, settings.readingSpeed, stop, supported])

  const pause = useCallback(() => {
    if (!supported || speechState !== 'speaking' || !audioRef.current) return
    audioRef.current.pause()
    setSpeechState('paused')
  }, [speechState, supported])

  const resume = useCallback(async () => {
    if (!supported || speechState !== 'paused' || !audioRef.current) return
    try {
      await audioRef.current.play()
      setSpeechState('speaking')
    } catch {
      setSpeechState('error')
      setSpeechError('Piper audio could not resume.')
    }
  }, [speechState, supported])

  useEffect(() => stop, [stop])
  useEffect(() => {
    if (!settings.readAloud) stop()
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
  return {
    supported: context.supported,
    state: isActive ? context.speechState : 'idle',
    error: context.speechError,
    play: () => context.speak(id, content),
    pause: context.pause,
    resume: context.resume,
    stop: context.stop,
  }
}
