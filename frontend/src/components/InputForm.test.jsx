import { render, screen } from '@testing-library/react'
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
})
