import { useAccessibilitySettings } from '../../accessibility/AccessibilityContext.jsx'

export const PRESET_OPTIONS = [
  { id: 'standard', label: 'Standard', description: 'Keep the original vibego experience.' },
  { id: 'easyReading', label: 'Easy Reading', description: 'Simple sans-serif type, larger text, calm spacing, and reading tools.' },
  { id: 'senior', label: 'Senior Mode', description: 'Extra-large text, strong contrast, big controls, and a simplified layout.' },
  { id: 'voiceFirst', label: 'Voice First', description: 'Put read-aloud and guided voice tools within easy reach.' },
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
