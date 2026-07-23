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

function createSilentWavUrl() {
  const sampleRate = 8000
  const sampleCount = 400
  const buffer = new ArrayBuffer(44 + sampleCount)
  const view = new DataView(buffer)
  const writeText = (offset, value) => {
    for (let index = 0; index < value.length; index += 1) {
      view.setUint8(offset + index, value.charCodeAt(index))
    }
  }
  writeText(0, 'RIFF')
  view.setUint32(4, 36 + sampleCount, true)
  writeText(8, 'WAVE')
  writeText(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate, true)
  view.setUint16(32, 1, true)
  view.setUint16(34, 8, true)
  writeText(36, 'data')
  view.setUint32(40, sampleCount, true)
  for (let index = 44; index < buffer.byteLength; index += 1) view.setUint8(index, 128)
  return URL.createObjectURL(new Blob([buffer], { type: 'audio/wav' }))
}

export function TextToSpeechProvider({ children }) {
  const { settings } = useAccessibilitySettings()
  const [activeId, setActiveId] = useState(null)
  const [speechState, setSpeechState] = useState('idle')
  const [speechError, setSpeechError] = useState('')
  const [speechEngine, setSpeechEngine] = useState(null)
  const audioRef = useRef(null)
  const audioUrlRef = useRef('')
  const browserUtteranceRef = useRef(null)
  const requestRef = useRef(null)
  const requestVersionRef = useRef(0)
  const requiresReadAloudRef = useRef(false)
  const piperPlaybackSupported = typeof window !== 'undefined'
    && typeof window.Audio === 'function'
    && typeof URL !== 'undefined'
    && typeof URL.createObjectURL === 'function'
    && typeof URL.revokeObjectURL === 'function'
  const browserSpeechSupported = typeof window !== 'undefined'
    && typeof window.speechSynthesis?.speak === 'function'
    && typeof window.SpeechSynthesisUtterance === 'function'
  const supported = browserSpeechSupported || piperPlaybackSupported

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

  const releaseBrowserSpeech = useCallback(() => {
    const utterance = browserUtteranceRef.current
    if (utterance) {
      utterance.onstart = null
      utterance.onend = null
      utterance.onerror = null
      utterance.onpause = null
      utterance.onresume = null
    }
    browserUtteranceRef.current = null
    if (typeof window !== 'undefined' && window.speechSynthesis && utterance) {
      window.speechSynthesis.cancel()
    }
  }, [])

  const stop = useCallback(() => {
    requestVersionRef.current += 1
    requestRef.current?.abort()
    requestRef.current = null
    releaseAudio()
    releaseBrowserSpeech()
    setActiveId(null)
    setSpeechState('idle')
    setSpeechError('')
    setSpeechEngine(null)
    requiresReadAloudRef.current = false
  }, [releaseAudio, releaseBrowserSpeech])

  const speak = useCallback(async (id, content, {
    force = false,
    language,
    userInitiated = false,
  } = {}) => {
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
    setSpeechEngine(null)

    // Prefer the browser's built-in speech engine. It works on localhost without
    // Docker, FastAPI, or a network request, and honors the same language/rate
    // controls as the local Piper service.
    if (browserSpeechSupported) {
      try {
        const synth = window.speechSynthesis
        const utterance = new window.SpeechSynthesisUtterance(preparedText)
        const requestedLanguage = String(language || speechLanguage()).toLowerCase()
        const languagePrefix = requestedLanguage.startsWith('zh') ? 'zh' : 'en'
        utterance.lang = languagePrefix === 'zh' ? 'zh-CN' : 'en-US'
        utterance.rate = settings.readingSpeed

        const voices = synth.getVoices?.() || []
        utterance.voice = voices.find((voice) => (
          voice.localService && voice.lang?.toLowerCase().startsWith(languagePrefix)
        )) || voices.find((voice) => voice.lang?.toLowerCase().startsWith(languagePrefix)) || null

        browserUtteranceRef.current = utterance
        setSpeechEngine('browser')
        utterance.onstart = () => {
          setActiveId(id)
          setSpeechState('speaking')
        }
        utterance.onpause = () => setSpeechState('paused')
        utterance.onresume = () => setSpeechState('speaking')
        utterance.onend = () => {
          browserUtteranceRef.current = null
          setActiveId(null)
          setSpeechState('idle')
          setSpeechEngine(null)
          requiresReadAloudRef.current = false
        }
        utterance.onerror = (event) => {
          browserUtteranceRef.current = null
          setActiveId(id)
          setSpeechState('error')
          setSpeechError(
            event?.error
              ? `The browser voice could not play (${event.error}).`
              : 'The browser voice could not play.',
          )
          setSpeechEngine('browser')
        }
        if (synth.paused) synth.resume()
        synth.speak(utterance)
        // Some engines queue speech before emitting `start`; expose a useful
        // state immediately so controls do not remain stuck on "Preparing".
        setSpeechState('speaking')
        return
      } catch {
        releaseBrowserSpeech()
        // Older or partially implemented browsers can expose the API but throw
        // on use. Continue to the Piper compatibility path below.
      }
    }

    if (!piperPlaybackSupported) {
      setSpeechState('error')
      setSpeechError('Speech playback is unavailable in this browser.')
      return
    }

    let audio = null
    let unlockUrl = ''
    if (userInitiated) {
      unlockUrl = createSilentWavUrl()
      audio = new window.Audio(unlockUrl)
      audio.preload = 'auto'
      audioRef.current = audio
      audioUrlRef.current = unlockUrl
      // Start a silent clip inside the trusted click. This keeps the same audio
      // element authorized while the local Piper request finishes.
      audio.play().catch(() => {})
    }

    try {
      const blob = await synthesizeSpeech(preparedText, {
        language: language || speechLanguage(),
        speed: settings.readingSpeed,
        signal: controller.signal,
      })
      if (controller.signal.aborted || requestVersion !== requestVersionRef.current) return

      const audioUrl = URL.createObjectURL(blob)
      if (audio) {
        audio.pause()
        URL.revokeObjectURL(unlockUrl)
        audioUrlRef.current = ''
        audio.src = audioUrl
        audio.load?.()
      } else {
        audio = new window.Audio(audioUrl)
      }
      audio.preload = 'auto'
      audioUrlRef.current = audioUrl
      audioRef.current = audio
      setSpeechEngine('piper')
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
        setSpeechEngine('piper')
      }
      await audio.play()
    } catch (error) {
      if (controller.signal.aborted || requestVersion !== requestVersionRef.current) return
      releaseAudio()
      setActiveId(id)
      setSpeechState('error')
      setSpeechError(error?.message || 'Piper voice is unavailable.')
      setSpeechEngine('piper')
    } finally {
      if (requestRef.current === controller) requestRef.current = null
    }
  }, [
    browserSpeechSupported,
    piperPlaybackSupported,
    releaseAudio,
    releaseBrowserSpeech,
    settings.readAloud,
    settings.readingSpeed,
    stop,
    supported,
  ])

  const pause = useCallback(() => {
    if (speechState !== 'speaking') return
    if (speechEngine === 'browser' && browserUtteranceRef.current) {
      window.speechSynthesis.pause()
      setSpeechState('paused')
      return
    }
    if (!audioRef.current) return
    audioRef.current.pause()
    setSpeechState('paused')
  }, [speechEngine, speechState])

  const resume = useCallback(async () => {
    if (speechState !== 'paused') return
    if (speechEngine === 'browser' && browserUtteranceRef.current) {
      window.speechSynthesis.resume()
      setSpeechState('speaking')
      return
    }
    if (!audioRef.current) return
    try {
      await audioRef.current.play()
      setSpeechState('speaking')
    } catch {
      setSpeechState('error')
      setSpeechError('Piper audio could not resume.')
    }
  }, [speechEngine, speechState])

  useEffect(() => stop, [stop])
  useEffect(() => {
    if (!settings.readAloud && requiresReadAloudRef.current) stop()
  }, [settings.readAloud, stop])

  const value = useMemo(() => ({
    supported,
    activeId,
    speechState,
    speechError,
    speechEngine,
    speak,
    pause,
    resume,
    stop,
  }), [supported, activeId, speechState, speechError, speechEngine, speak, pause, resume, stop])

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
    (options) => context.speak(id, content, options),
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
    engine: isActive ? context.speechEngine : null,
    play,
    playText,
    pause: context.pause,
    resume: context.resume,
    stop: context.stop,
  }
}
