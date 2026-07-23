import { useState } from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, vi } from 'vitest'
import { synthesizeSpeech } from '../../api.js'
import { ACCESSIBILITY_STORAGE_KEY, AccessibilityProvider } from '../../accessibility/AccessibilityContext.jsx'
import { TextToSpeechProvider } from '../../hooks/useTextToSpeech.js'
import MapView from '../MapView.jsx'
import ConfirmationDialog from './ConfirmationDialog.jsx'
import EmergencyInformation from './EmergencyInformation.jsx'
import NextStepHelper from './NextStepHelper.jsx'

vi.mock('../../api.js', () => ({ synthesizeSpeech: vi.fn() }))

beforeEach(() => {
  synthesizeSpeech.mockResolvedValue(new Blob([new Uint8Array(64)], { type: 'audio/wav' }))
  URL.createObjectURL = vi.fn(() => 'blob:piper-senior')
  URL.revokeObjectURL = vi.fn()
  window.Audio = class Audio {
    play = vi.fn(async () => this.onplay?.())
    pause = vi.fn()
    removeAttribute = vi.fn()
    load = vi.fn()
  }
})

function renderSenior(children) {
  localStorage.setItem(ACCESSIBILITY_STORAGE_KEY, JSON.stringify({
    preset: 'senior',
    onboardingComplete: true,
    readAloud: true,
    readingSpeed: 0.9,
  }))
  return render(
    <AccessibilityProvider>
      <TextToSpeechProvider>{children}</TextToSpeechProvider>
    </AccessibilityProvider>,
  )
}

describe('Senior Mode trip helpers', () => {
  it('shows a readable emergency card and reads it on request', async () => {
    const user = userEvent.setup()
    renderSenior(
      <EmergencyInformation result={{
        agent_outputs: { housing: { recommended: { name: 'Harbor Hotel', address: '8 River Road', phone: '+1 555 0100' } } },
        local_emergency_number: '112',
      }} />,
    )

    await user.click(screen.getByRole('button', { name: 'Emergency Information' }))
    expect(screen.getByRole('dialog', { name: 'Emergency Information' })).toBeVisible()
    expect(screen.getByText('Harbor Hotel')).toBeVisible()
    expect(screen.getByText('8 River Road')).toBeVisible()
    expect(screen.getByText('112')).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Read emergency information aloud' }))
    await waitFor(() => expect(synthesizeSpeech).toHaveBeenCalledOnce())
    expect(synthesizeSpeech.mock.calls[0][0]).toContain('Harbor Hotel')
  })

  it('opens a very short immediate-next-step dialog', async () => {
    const user = userEvent.setup()
    renderSenior(
      <NextStepHelper result={{
        schedule: [{ day: 1, date: '2026-07-22', items: [{ time: '11:30', title: 'Board Train 2', detail: 'Walk 4 minutes. Ride 3 stops.' }] }],
      }} />,
    )
    await user.click(screen.getByRole('button', { name: 'What do I do next?' }))
    expect(screen.getByRole('dialog', { name: 'Do this next' })).toBeVisible()
    expect(screen.getByText('Board Train 2')).toBeVisible()
    expect(screen.getByText('Walk 4 minutes.')).toBeVisible()
  })

  it('starts with three clearly labeled place choices and can reveal all results', async () => {
    const user = userEvent.setup()
    const points = [
      { label: 'Harbor Hotel', type: 'housing', area: 'Center', lat: 1, lng: 1 },
      { label: 'Museum', type: 'activity', area: 'North', lat: 1.01, lng: 1.01 },
      { label: 'Garden', type: 'activity', area: 'West', lat: 2, lng: 2 },
      { label: 'Market', type: 'activity', area: 'South', lat: 3, lng: 3 },
    ]
    renderSenior(<MapView points={points} agentOutputs={{ activity: { recommended: [
      { name: 'Museum', price: 25 }, { name: 'Garden', price: 5 }, { name: 'Market', price: 20 },
    ] } }} />)

    expect(screen.getByText('Top Recommendation')).toBeVisible()
    expect(screen.getByText('Best Value')).toBeVisible()
    expect(screen.getByText('Closest')).toBeVisible()
    const showAll = screen.getByRole('button', { name: 'Show all 4 places' })
    expect(showAll).toHaveAttribute('aria-expanded', 'false')
    await user.click(showAll)
    expect(screen.getByRole('button', { name: 'Show fewer places' })).toHaveAttribute('aria-expanded', 'true')
  })
})

function ConfirmationHarness({ onConfirm }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>Start a new journey</button>
      <ConfirmationDialog
        open={open}
        title="Start a new journey?"
        description="Your current trip will leave this screen."
        onCancel={() => setOpen(false)}
        onConfirm={onConfirm}
      />
    </>
  )
}

describe('Senior Mode confirmation', () => {
  it('uses plain actions, closes with Cancel, and returns focus', async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    render(<ConfirmationHarness onConfirm={onConfirm} />)
    const trigger = screen.getByRole('button', { name: 'Start a new journey' })
    await user.click(trigger)
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus()
    expect(screen.getByRole('button', { name: 'Continue' })).toBeEnabled()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(trigger).toHaveFocus()
    expect(onConfirm).not.toHaveBeenCalled()
  })
})
