import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ProgressTracker from './ProgressTracker.jsx'


const AGENTS = ['budget', 'transportation', 'housing', 'food', 'activity', 'planning', 'orchestrator']


describe('Agent Town planning progress', () => {
  it('maps live agent events into residents, handoffs, and the town channel', () => {
    render(
      <ProgressTracker
        agents={AGENTS}
        statuses={{ budget: 'done', transportation: 'running' }}
        events={[
          { agent: 'budget', type: 'done', output: { reasoning: 'Food and lodging caps are ready.' } },
          { agent: 'transportation', type: 'start' },
        ]}
        trip={{ origin: 'Shanghai', location: 'Milan, Italy' }}
        error={null}
        onRetry={() => {}}
      />,
    )

    expect(screen.getByRole('region', { name: 'Live Agent Town planning session' })).toBeVisible()
    expect(screen.getByLabelText('Planning from Shanghai to Milan, Italy')).toBeVisible()
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '14')
    expect(screen.getAllByText('handoff sent').length).toBeGreaterThan(0)
    expect(screen.getByRole('log')).toHaveTextContent('Comparing routes, times, and arrival points.')
  })

  it('shows an active resident as paused and preserves the retry action', async () => {
    const user = userEvent.setup()
    const onRetry = vi.fn()
    render(
      <ProgressTracker
        agents={AGENTS}
        statuses={{ budget: 'done', transportation: 'running' }}
        events={[{ agent: 'transportation', type: 'start' }]}
        trip={{ origin: 'Shanghai', location: 'Milan, Italy' }}
        error="Provider paused"
        onRetry={onRetry}
      />,
    )

    expect(screen.getAllByText('Paused').length).toBeGreaterThan(0)
    expect(screen.getByRole('alert')).toHaveTextContent('Provider paused')
    await user.click(screen.getByRole('button', { name: /Return to trip brief/ }))
    expect(onRetry).toHaveBeenCalledOnce()
  })
})
