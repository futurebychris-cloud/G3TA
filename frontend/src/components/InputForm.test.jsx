import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { AccessibilityProvider } from '../accessibility/AccessibilityContext.jsx'
import InputForm from './InputForm.jsx'

describe('trip input accessibility', () => {
  it('provides labels and keyboard-operable preference controls', async () => {
    const user = userEvent.setup()
    render(
      <AccessibilityProvider>
        <InputForm onSubmit={vi.fn()} />
      </AccessibilityProvider>,
    )

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

  it('submits traveler count, must-go places, and budget preferences', async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(
      <AccessibilityProvider>
        <InputForm onSubmit={onSubmit} />
      </AccessibilityProvider>,
    )

    await user.type(screen.getByRole('textbox', { name: /Going to/ }), 'Shanghai')
    await user.clear(screen.getByRole('spinbutton', { name: /Travelers/ }))
    await user.type(screen.getByRole('spinbutton', { name: /Travelers/ }), '3')
    await user.type(screen.getByRole('textbox', { name: /Must-go places/ }), 'The Bund, Yu Garden')
    await user.selectOptions(screen.getByRole('combobox', { name: /Main budget priority/ }), 'food')
    await user.click(screen.getByRole('button', { name: 'Design my journey' }))

    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      num_people: 3,
      is_group: true,
      must_go_sites: ['The Bund', 'Yu Garden'],
      preferences: expect.objectContaining({
        budget_priority: { food: 1.5 },
      }),
    }))
  })
})
