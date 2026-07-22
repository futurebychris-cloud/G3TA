import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App.jsx'
import { AccessibilityProvider } from './accessibility/AccessibilityContext.jsx'
import { ACCESSIBILITY_STORAGE_KEY } from './accessibility/AccessibilityContext.jsx'
import { TextToSpeechProvider } from './hooks/useTextToSpeech.js'

describe('app accessibility entry point', () => {
  it('shows the accessibility button in the header and opens its options', async () => {
    const user = userEvent.setup()
    localStorage.setItem(ACCESSIBILITY_STORAGE_KEY, JSON.stringify({ onboardingComplete: true }))
    render(
      <AccessibilityProvider>
        <TextToSpeechProvider><App /></TextToSpeechProvider>
      </AccessibilityProvider>,
    )
    const header = screen.getByRole('banner')
    const trigger = screen.getByRole('button', { name: 'Accessibility options' })
    expect(header).toContainElement(trigger)
    await user.click(trigger)
    expect(screen.getByRole('dialog', { name: 'Accessibility options' })).toBeVisible()
    expect(screen.getByRole('checkbox', { name: /Bigger Text/ })).toBeEnabled()
    expect(screen.getByRole('radio', { name: 'Senior Mode' })).toBeEnabled()
    await user.click(screen.getByRole('button', { name: 'Open guided setup' }))
    expect(await screen.findByRole('dialog', { name: 'Voice-guided trip setup' })).toBeVisible()
    expect(screen.getByText('Question 1 of 11')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Answer flying from by voice' })).toBeDisabled()
    expect(screen.getAllByRole('status').some((status) => status.textContent.includes('Voice input is unavailable'))).toBe(true)
  })
})
