import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

export const ACCESSIBILITY_STORAGE_KEY = 'g3ta-accessibility-settings-v1'

export const DEFAULT_ACCESSIBILITY_SETTINGS = Object.freeze({
  preset: 'standard',
  onboardingComplete: false,
  easyReading: false,
  largerText: false,
  extraTextSpacing: false,
  highContrast: false,
  reducedMotion: false,
  dyslexiaFont: false,
  lineFocus: 'off',
  readAloud: false,
  readingSpeed: 1,
})

export const ACCESSIBILITY_PRESETS = Object.freeze({
  standard: {},
  easyReading: {
    easyReading: true,
    lineFocus: 'one',
  },
  senior: {
    easyReading: true,
    largerText: true,
    extraTextSpacing: true,
    highContrast: true,
    reducedMotion: true,
    dyslexiaFont: true,
    lineFocus: 'three',
    readAloud: true,
    readingSpeed: 0.9,
  },
  voiceFirst: {
    readAloud: true,
    readingSpeed: 1,
  },
})

const BOOLEAN_KEYS = [
  'easyReading',
  'largerText',
  'extraTextSpacing',
  'highContrast',
  'reducedMotion',
  'dyslexiaFont',
  'readAloud',
]
const LINE_FOCUS_VALUES = new Set(['off', 'one', 'three'])
const PRESET_VALUES = new Set(Object.keys(ACCESSIBILITY_PRESETS))
const AccessibilityContext = createContext(null)

export function normalizeAccessibilitySettings(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return { ...DEFAULT_ACCESSIBILITY_SETTINGS }
  }
  const normalized = { ...DEFAULT_ACCESSIBILITY_SETTINGS }
  BOOLEAN_KEYS.forEach((key) => {
    if (typeof value[key] === 'boolean') normalized[key] = value[key]
  })
  if (PRESET_VALUES.has(value.preset)) normalized.preset = value.preset
  if (typeof value.onboardingComplete === 'boolean') normalized.onboardingComplete = value.onboardingComplete
  if (LINE_FOCUS_VALUES.has(value.lineFocus)) normalized.lineFocus = value.lineFocus
  const hasNumericSpeed = typeof value.readingSpeed === 'number'
    || (typeof value.readingSpeed === 'string' && value.readingSpeed.trim() !== '')
  const speed = hasNumericSpeed ? Number(value.readingSpeed) : Number.NaN
  if (Number.isFinite(speed)) normalized.readingSpeed = Math.min(1.5, Math.max(0.6, speed))
  return normalized
}

function loadSettings() {
  try {
    return normalizeAccessibilitySettings(JSON.parse(window.localStorage.getItem(ACCESSIBILITY_STORAGE_KEY)))
  } catch {
    return { ...DEFAULT_ACCESSIBILITY_SETTINGS }
  }
}

export function applyAccessibilityState(root, settings) {
  if (!root) return
  root.dataset.easyReading = String(settings.easyReading)
  root.dataset.largerText = String(settings.largerText)
  root.dataset.extraTextSpacing = String(settings.extraTextSpacing)
  root.dataset.highContrast = String(settings.highContrast)
  root.dataset.reducedMotion = String(settings.reducedMotion)
  root.dataset.dyslexiaFont = String(settings.dyslexiaFont)
  root.dataset.lineFocus = settings.lineFocus
  root.dataset.accessibilityPreset = settings.preset
}

export function AccessibilityProvider({ children }) {
  const [settings, setSettings] = useState(loadSettings)

  useEffect(() => {
    applyAccessibilityState(document.documentElement, settings)
    try {
      window.localStorage.setItem(ACCESSIBILITY_STORAGE_KEY, JSON.stringify(settings))
    } catch {
      // Settings remain active for this session when storage is blocked or full.
    }
  }, [settings])

  const setSetting = useCallback((key, value) => {
    setSettings((current) => normalizeAccessibilitySettings({ ...current, [key]: value }))
  }, [])

  const resetSettings = useCallback(() => {
    setSettings((current) => ({
      ...DEFAULT_ACCESSIBILITY_SETTINGS,
      onboardingComplete: current.onboardingComplete,
    }))
  }, [])

  const applyPreset = useCallback((preset) => {
    if (!PRESET_VALUES.has(preset)) return
    setSettings((current) => ({
      ...DEFAULT_ACCESSIBILITY_SETTINGS,
      ...ACCESSIBILITY_PRESETS[preset],
      preset,
      onboardingComplete: current.onboardingComplete,
    }))
  }, [])

  const completeOnboarding = useCallback(() => {
    setSettings((current) => ({ ...current, onboardingComplete: true }))
  }, [])

  const value = useMemo(() => ({
    settings,
    setSetting,
    resetSettings,
    applyPreset,
    completeOnboarding,
  }), [settings, setSetting, resetSettings, applyPreset, completeOnboarding])
  return <AccessibilityContext.Provider value={value}>{children}</AccessibilityContext.Provider>
}

export function useAccessibilitySettings() {
  const context = useContext(AccessibilityContext)
  if (!context) throw new Error('useAccessibilitySettings must be used inside AccessibilityProvider')
  return context
}
