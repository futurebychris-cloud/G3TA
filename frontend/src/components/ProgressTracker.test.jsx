import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import ProgressTracker from './ProgressTracker.jsx'

describe('ProgressTracker live sub-stages', () => {
  it('shows the current provider stage and elapsed time', () => {
    render(
      <ProgressTracker
        agents={['transportation']}
        statuses={{ transportation: 'running' }}
        events={[{
          type: 'progress',
          agent: 'transportation',
          detail: '正在查询航班与实时票价',
          elapsed_seconds: 12,
        }]}
        trip={{ origin: 'Shanghai', location: 'New York' }}
        error={null}
        onRetry={vi.fn()}
      />,
    )

    expect(screen.getByText('Working · 12s')).toBeInTheDocument()
    expect(screen.getAllByText('正在查询航班与实时票价').length).toBeGreaterThan(0)
  })
})
