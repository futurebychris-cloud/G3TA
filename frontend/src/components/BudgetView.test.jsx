import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import BudgetView from './BudgetView.jsx'

describe('BudgetView', () => {
  it('keeps the category breakdown without rendering expense details', () => {
    render(
      <BudgetView
        cost={{
          breakdown: { transportation: 730, food: 364.25 },
          total: 1094.25,
          budget: 2500,
          currency: 'USD',
          within_budget: true,
          expense_items: [
            {
              category: 'transportation',
              label: 'Intercity transport',
              detail: 'Flight option 1',
              currency: 'USD',
              amount: 730,
            },
          ],
        }}
        budgetAgent={{}}
      />,
    )

    expect(screen.getByRole('heading', { name: 'Cost breakdown' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Expense details' })).not.toBeInTheDocument()
    expect(screen.queryByText('Intercity transport')).not.toBeInTheDocument()
  })
})
