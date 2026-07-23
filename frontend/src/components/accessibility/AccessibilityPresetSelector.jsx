import { useAccessibilitySettings } from '../../accessibility/AccessibilityContext.jsx'

export const PRESET_OPTIONS = [
  { id: 'standard', label: 'Standard', description: 'Keep the original G3TA experience.' },
  { id: 'easyReading', label: 'Easy Reading', description: 'Use plain presentation and one-line focus.' },
  { id: 'senior', label: 'Senior Mode', description: 'Larger, calmer, clearer, and more forgiving.' },
  { id: 'voiceFirst', label: 'Voice First', description: 'Open voice/text trip setup and enable local Piper read aloud.' },
]

export default function AccessibilityPresetSelector({ compact = false, onSelect }) {
  const { settings, applyPreset } = useAccessibilitySettings()

  function select(preset) {
    applyPreset(preset)
    onSelect?.(preset)
  }

  return (
    <fieldset className={compact ? 'preset-selector compact' : 'preset-selector'}>
      <legend className="sr-only">Choose an accessibility preset</legend>
      <div className="preset-grid">
        {PRESET_OPTIONS.map((option) => (
          <label key={option.id} className="preset-option">
            <input
              type="radio"
              name={compact ? 'quick-accessibility-preset' : 'accessibility-preset'}
              value={option.id}
              checked={settings.preset === option.id}
              onChange={() => select(option.id)}
            />
            <span>
              <strong>{option.label}</strong>
              {!compact && <small>{option.description}</small>}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  )
}
