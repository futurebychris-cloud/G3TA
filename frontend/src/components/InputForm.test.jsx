import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import InputForm from './InputForm.jsx'

describe('trip input accessibility', () => {
  it('provides labels and keyboard-operable preference controls', async () => {
    const user = userEvent.setup()
    render(<InputForm onSubmit={vi.fn()} />)

    expect(screen.getByRole('textbox', { name: /Flying from/ })).toBeRequired()
    expect(screen.getByRole('textbox', { name: /Going to/ })).toBeRequired()
    expect(screen.getByLabelText('Start date')).toBeRequired()
    expect(screen.getByLabelText('End date')).toBeRequired()
    expect(screen.getByRole('button', { name: 'Design my journey' })).toBeEnabled()

    const japanese = screen.getByRole('button', { name: /Japanese not selected/ })
    japanese.focus()
    await user.keyboard('{Enter}')
    expect(japanese).toHaveAttribute('aria-pressed', 'true')
    expect(japanese).toHaveAccessibleName(/Japanese selected/)
  })

  it('accepts a guided draft as an add-on while keeping the standard form editable', async () => {
    const draft = {
      origin: 'Paris',
      location: 'Lisbon',
      dates: { start: '2026-09-02', end: '2026-09-07' },
      budget: { total: 1800, currency: 'EUR' },
      preferences: { bites: [], transportation_type: ['train'], activity_style: ['relaxed'] },
      time_constraints: '',
      must_go_sites: ['Belém Tower'],
      num_people: 2,
    }
    render(
      <InputForm
        onSubmit={vi.fn()}
        intakeDraft={draft}
        intakeNotice={{ summary: 'A relaxed Lisbon trip for two.', missing: [] }}
      />,
    )

    expect(await screen.findByText('Your guided draft is in the normal form')).toBeVisible()
    await waitFor(() => expect(screen.getByRole('textbox', { name: /Flying from/ })).toHaveValue('Paris'))
    expect(screen.getByRole('textbox', { name: /Going to/ })).toHaveValue('Lisbon')
    expect(screen.getByLabelText('Budget amount')).toHaveValue(1800)
    expect(screen.getByRole('button', { name: /Design my journey/ })).toBeEnabled()
  })
})
