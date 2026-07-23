import {
  BedDouble,
  BrainCircuit,
  Calculator,
  Check,
  Compass,
  LoaderCircle,
  MapPinned,
  Plane,
  RefreshCw,
  Utensils,
} from 'lucide-react'
import AgentTown from './AgentTown.jsx'

const META = {
  budget: { label: 'Budget architect', note: 'Setting sensible category limits', icon: Calculator },
  transportation: { label: 'Route scout', note: 'Comparing the best ways there', icon: Plane },
  housing: { label: 'Stay curator', note: 'Finding your home away from home', icon: BedDouble },
  food: { label: 'Taste editor', note: 'Mapping meals to your preferences', icon: Utensils },
  activity: { label: 'Experience scout', note: 'Selecting the moments worth keeping', icon: MapPinned },
  planning: { label: 'Journey editor', note: 'Balancing weather, pace, and packing', icon: Compass },
  orchestrator: { label: 'Lead orchestrator', note: 'Composing every idea into one plan', icon: BrainCircuit },
}

export default function ProgressTracker({ agents, statuses, events, trip, error, onRetry }) {
  const visibleAgents = agents.filter((agent) => META[agent])
  const statusFor = (agent) => error && statuses[agent] === 'running' ? 'paused' : (statuses[agent] || 'pending')
  const doneCount = visibleAgents.filter((agent) => statusFor(agent) === 'done').length
  const percentage = Math.round((doneCount / Math.max(visibleAgents.length, 1)) * 100)
  const activeAgents = error ? [] : visibleAgents.filter((agent) => statusFor(agent) === 'running')

  return (
    <section
      className="progress-stage progress-stage--town"
      aria-labelledby="planning-progress-heading"
      aria-busy={!error && percentage < 100}
    >
      <h1 id="planning-progress-heading" className="sr-only">Your trip is taking shape</h1>
      <div className="progress-town-shell">
        <AgentTown agents={visibleAgents} statuses={statuses} events={events} trip={trip} paused={Boolean(error)} />
        <div className="progress-town-footer">
          <p aria-live="polite" aria-atomic="true">
            {error
              ? 'The town session is paused. Your completed handoffs are still safe.'
              : activeAgents.length
                ? `${activeAgents.map((agent) => META[agent].label).join(', ')} ${activeAgents.length === 1 ? 'is' : 'are'} talking through the plan now.`
                : 'Connecting the team and preparing your brief.'}
          </p>
          <div className="progress-meter">
            <div className="progress-meter-label"><span>{percentage}% composed</span><span>{doneCount} of {visibleAgents.length}</span></div>
            <div
              className="progress-track"
              role="progressbar"
              aria-label="Trip planning progress"
              aria-valuenow={percentage}
              aria-valuemin="0"
              aria-valuemax="100"
            >
              <span style={{ width: `${percentage}%` }} />
            </div>
          </div>
        </div>
      </div>

      <div className="agent-board">
        <div className="agent-board-head">
          <div>
            <span className="section-index">TOWN ROSTER</span>
            <h2>Who is working</h2>
          </div>
          <span className={`live-badge${error ? ' paused' : ''}`} aria-live="polite">
            <span className="live-pulse" aria-hidden="true" /> {error ? 'Paused' : 'Live status'}
          </span>
        </div>

        <ol className="agent-list">
          {visibleAgents.map((agent, index) => {
            const status = statusFor(agent)
            const { label, note, icon: AgentIcon } = META[agent]
            return (
              <li key={agent} className={`agent-row ${status}`}>
                <span className="agent-number">{String(index + 1).padStart(2, '0')}</span>
                <span className="agent-icon" aria-hidden="true"><AgentIcon size={19} strokeWidth={1.8} /></span>
                <span className="agent-copy"><strong>{label}</strong><small>{note}</small></span>
                <span className="agent-state" aria-live={status === 'running' ? 'polite' : undefined}>
                  {status === 'done' && <><Check size={15} /> Complete</>}
                  {status === 'running' && <><LoaderCircle className="spinner" size={15} /> Thinking</>}
                  {status === 'paused' && 'Paused'}
                  {status === 'pending' && 'Queued'}
                </span>
              </li>
            )
          })}
        </ol>

        {error && (
          <div className="progress-error" role="alert">
            <strong>The planning session paused.</strong>
            <p>{error}</p>
            <button type="button" onClick={onRetry}><RefreshCw size={16} /> Return to trip brief</button>
          </div>
        )}

        {!error && <p className="progress-note">Keep this window open — the finished itinerary will appear automatically.</p>}
      </div>
    </section>
  )
}
