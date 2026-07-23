import { useState } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
  ACCESSIBILITY_STORAGE_KEY,
  AccessibilityProvider,
  DEFAULT_ACCESSIBILITY_SETTINGS,
  normalizeAccessibilitySettings,
  useAccessibilitySettings,
} from './AccessibilityContext.jsx'
import AccessibilityPanel from '../components/accessibility/AccessibilityPanel.jsx'
import AccessibilityOnboarding from '../components/accessibility/AccessibilityOnboarding.jsx'

function SettingsHarness() {
  const { settings, setSetting, resetSettings, applyPreset } = useAccessibilitySettings()
  return (
    <div>
      <output data-testid="settings">{JSON.stringify(settings)}</output>
      <button type="button" onClick={() => setSetting('largerText', !settings.largerText)}>Toggle bigger text</button>
      <button type="button" onClick={() => setSetting('highContrast', true)}>Enable contrast</button>
      <button type="button" onClick={resetSettings}>Reset settings</button>
      <button type="button" onClick={() => applyPreset('easyReading')}>Use Easy Reading</button>
      <button type="button" onClick={() => applyPreset('senior')}>Use Senior Mode</button>
    </div>
  )
}

function PanelHarness() {
  const [open, setOpen] = useState(false)
  return (
    <AccessibilityProvider>
      <button type="button" onClick={() => setOpen(true)}>Accessibility options</button>
      <AccessibilityPanel open={open} onClose={() => setOpen(false)} />
    </AccessibilityProvider>
  )
}

describe('accessibility settings', () => {
  it('enables, disables, persists, applies CSS state, and resets settings', async () => {
    const user = userEvent.setup()
    render(<AccessibilityProvider><SettingsHarness /></AccessibilityProvider>)

    // Senior Mode ships on by default, so the first toggle turns bigger text OFF.
    await user.click(screen.getByRole('button', { name: 'Toggle bigger text' }))
    expect(document.documentElement).toHaveAttribute('data-larger-text', 'false')
    expect(JSON.parse(localStorage.getItem(ACCESSIBILITY_STORAGE_KEY)).largerText).toBe(false)

    await user.click(screen.getByRole('button', { name: 'Toggle bigger text' }))
    expect(document.documentElement).toHaveAttribute('data-larger-text', 'true')

    await user.click(screen.getByRole('button', { name: 'Use Easy Reading' }))
    await user.click(screen.getByRole('button', { name: 'Reset settings' }))
    await waitFor(() => expect(JSON.parse(screen.getByTestId('settings').textContent)).toEqual(DEFAULT_ACCESSIBILITY_SETTINGS))
    // Reset lands back on the Senior Mode defaults, contrast included.
    expect(document.documentElement).toHaveAttribute('data-high-contrast', 'true')
  })

  it('loads valid saved settings and rejects invalid saved values', () => {
    localStorage.setItem(ACCESSIBILITY_STORAGE_KEY, JSON.stringify({ largerText: false, lineFocus: 'invalid', readingSpeed: 99 }))
    render(<AccessibilityProvider><SettingsHarness /></AccessibilityProvider>)
    const loaded = JSON.parse(screen.getByTestId('settings').textContent)
    expect(loaded.largerText).toBe(false)
    // Invalid values fall back to the Senior Mode defaults.
    expect(loaded.lineFocus).toBe('three')
    expect(loaded.readingSpeed).toBe(1.5)
    expect(normalizeAccessibilitySettings('invalid')).toEqual(DEFAULT_ACCESSIBILITY_SETTINGS)
    expect(normalizeAccessibilitySettings({ readingSpeed: null }).readingSpeed).toBe(0.9)
  })

  it('applies Senior Mode as a preset and still allows individual overrides', async () => {
    const user = userEvent.setup()
    render(<AccessibilityProvider><SettingsHarness /></AccessibilityProvider>)
    await user.click(screen.getByRole('button', { name: 'Use Senior Mode' }))

    let current = JSON.parse(screen.getByTestId('settings').textContent)
    expect(current).toMatchObject({
      preset: 'senior',
      easyReading: true,
      largerText: true,
      extraTextSpacing: true,
      highContrast: true,
      reducedMotion: true,
      dyslexiaFont: true,
      lineFocus: 'three',
      readAloud: true,
      readingSpeed: 0.9,
    })
    expect(document.documentElement).toHaveAttribute('data-accessibility-preset', 'senior')

    await user.click(screen.getByRole('button', { name: 'Toggle bigger text' }))
    current = JSON.parse(screen.getByTestId('settings').textContent)
    expect(current.preset).toBe('senior')
    expect(current.largerText).toBe(false)
  })

  it('makes Easy Reading a clearly larger, simple-font reading preset', async () => {
    const user = userEvent.setup()
    render(<AccessibilityProvider><SettingsHarness /></AccessibilityProvider>)
    await user.click(screen.getByRole('button', { name: 'Use Easy Reading' }))

    expect(JSON.parse(screen.getByTestId('settings').textContent)).toMatchObject({
      preset: 'easyReading',
      easyReading: true,
      largerText: true,
      reducedMotion: true,
      dyslexiaFont: true,
      lineFocus: 'one',
      readAloud: true,
      readingSpeed: 0.95,
    })
    expect(document.documentElement).toHaveAttribute('data-accessibility-preset', 'easyReading')
    expect(document.documentElement).toHaveAttribute('data-larger-text', 'true')
    expect(document.documentElement).toHaveAttribute('data-dyslexia-font', 'true')
  })
})

describe('accessibility onboarding', () => {
  it('keeps the welcome chooser hidden and starts everyone in Senior Mode', () => {
    render(
      <AccessibilityProvider>
        <AccessibilityOnboarding />
        <SettingsHarness />
      </AccessibilityProvider>,
    )
    // The first-visit preset chooser is hidden (not deleted): Senior Mode is
    // simply the default, no dialog required.
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(document.documentElement).toHaveAttribute('data-accessibility-preset', 'senior')
    expect(JSON.parse(screen.getByTestId('settings').textContent).preset).toBe('senior')
  })
})

describe('accessibility panel', () => {
  it('opens with named controls, closes on Escape, and returns focus', async () => {
    const user = userEvent.setup()
    render(<PanelHarness />)
    const trigger = screen.getByRole('button', { name: 'Accessibility options' })
    await user.click(trigger)

    expect(screen.getByRole('dialog', { name: 'Accessibility options' })).toBeVisible()
    expect(screen.getByRole('checkbox', { name: /Easy Reading/ })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Close accessibility options' })).toHaveFocus()

    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
  })

  it('supports independent toggles and hides the preset and reset controls', async () => {
    const user = userEvent.setup()
    render(<PanelHarness />)
    await user.click(screen.getByRole('button', { name: 'Accessibility options' }))
    const easyReading = screen.getByRole('checkbox', { name: /Easy Reading/ })
    const contrast = screen.getByRole('checkbox', { name: /High Contrast/ })
    // Senior Mode defaults: both start checked, and each toggles independently.
    expect(easyReading).toBeChecked()
    expect(contrast).toBeChecked()
    await user.click(easyReading)
    expect(easyReading).not.toBeChecked()
    expect(contrast).toBeChecked()
    // Quick-setup presets and the reset button are hidden, not deleted.
    expect(screen.queryByRole('radio', { name: /Senior Mode/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reset to defaults' })).not.toBeInTheDocument()
  })
})
