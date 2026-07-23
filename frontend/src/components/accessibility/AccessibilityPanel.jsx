import { useRef } from 'react'
import { RotateCcw, X } from 'lucide-react'
import { useAccessibilitySettings } from '../../accessibility/AccessibilityContext.jsx'
import AccessibleDialog from './AccessibleDialog.jsx'
import AccessibilityPresetSelector from './AccessibilityPresetSelector.jsx'

const TOGGLES = [
  ['easyReading', 'Easy Reading', 'Shorter lines, plain presentation, and important details first.'],
  ['largerText', 'Bigger Text', 'Increase important text while keeping the layout responsive.'],
  ['extraTextSpacing', 'More Text Spacing', 'Add space between letters, words, lines, and paragraphs.'],
  ['highContrast', 'High Contrast', 'Use stronger colors, borders, and selected-state indicators.'],
  ['reducedMotion', 'Reduce Motion', 'Simplify nonessential movement and transitions.'],
  ['dyslexiaFont', 'Reading Font', 'Use an Arial, Verdana, and Tahoma system-font stack.'],
  ['readAloud', 'Read Aloud', 'Show speech controls on important travel results.'],
]

export default function AccessibilityPanel({ open, onClose, returnFocusRef }) {
  const { settings, setSetting, resetSettings } = useAccessibilitySettings()
  const closeRef = useRef(null)

  return (
    <AccessibleDialog
      open={open}
      onClose={onClose}
      returnFocusRef={returnFocusRef}
      initialFocusRef={closeRef}
      labelledBy="accessibility-title"
      describedBy="accessibility-description"
      className="accessibility-panel"
    >
        <header className="accessibility-panel-head">
          <div>
            <span className="section-index">MAKE IT YOURS</span>
            <h2 id="accessibility-title">Accessibility options</h2>
            <p id="accessibility-description">Choose only the reading and interaction tools that help you.</p>
          </div>
          <button ref={closeRef} className="dialog-close" type="button" onClick={onClose} aria-label="Close accessibility options">
            <X size={20} aria-hidden="true" />
          </button>
        </header>

        <div className="accessibility-presets-block">
          <span className="section-index">QUICK SETUP</span>
          <AccessibilityPresetSelector compact />
        </div>

        <div className="accessibility-options">
          {TOGGLES.map(([key, label, description]) => (
            <label className="setting-row" key={key}>
              <span className="setting-copy"><strong>{label}</strong><small>{description}</small></span>
              <span className="switch-control">
                <input
                  type="checkbox"
                  checked={settings[key]}
                  onChange={(event) => setSetting(key, event.target.checked)}
                />
                <span aria-hidden="true" />
              </span>
            </label>
          ))}

          <fieldset className="setting-fieldset">
            <legend>Line Focus</legend>
            <p>Highlight a sentence or a small group while you read longer sections.</p>
            <div className="segmented-control">
              {[['off', 'Off'], ['one', 'One line'], ['three', 'Three lines']].map(([value, label]) => (
                <label key={value}>
                  <input
                    type="radio"
                    name="line-focus"
                    value={value}
                    checked={settings.lineFocus === value}
                    onChange={() => setSetting('lineFocus', value)}
                  />
                  <span>{label}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <label className="speed-setting">
            <span className="setting-copy">
              <strong>Reading Speed</strong>
              <small>Controls local Piper read-aloud speed.</small>
            </span>
            <span className="speed-control">
              <input
                type="range"
                min="0.6"
                max="1.5"
                step="0.1"
                value={settings.readingSpeed}
                onChange={(event) => setSetting('readingSpeed', Number(event.target.value))}
                aria-label="Reading speed"
                aria-valuetext={`${settings.readingSpeed.toFixed(1)} times normal speed`}
              />
              <output>{settings.readingSpeed.toFixed(1)}×</output>
            </span>
          </label>
        </div>

        <footer className="accessibility-panel-actions">
          <button className="reset-accessibility" type="button" onClick={resetSettings}>
            <RotateCcw size={16} aria-hidden="true" /> Reset to defaults
          </button>
          <button className="done-accessibility" type="button" onClick={onClose}>Done</button>
        </footer>
    </AccessibleDialog>
  )
}
