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
import OrbitGlobe from './OrbitGlobe.jsx'

const META = {
  budget: { label: 'Budget architect', note: 'Setting sensible category limits', icon: Calculator },
  transportation: { label: 'Route scout', note: 'Comparing the best ways there', icon: Plane },
  housing: { label: 'Stay curator', note: 'Finding your home away from home', icon: BedDouble },
  food: { label: 'Taste editor', note: 'Mapping meals to your preferences', icon: Utensils },
  activity: { label: 'Experience scout', note: 'Selecting the moments worth keeping', icon: MapPinned },
  planning: { label: 'Journey editor', note: 'Balancing weather, pace, and packing', icon: Compass },
  orchestrator: { label: 'Lead orchestrator', note: 'Composing every idea into one plan', icon: BrainCircuit },
}

export default function ProgressTracker({ agents, statuses, error, onRetry }) {
  const doneCount = agents.filter((agent) => statuses[agent] === 'done').length
  const percentage = Math.round((doneCount / agents.length) * 100)
  const activeAgent = agents.find((agent) => statuses[agent] === 'running')

  return (
    <section className="progress-stage">
      <div className="progress-art">
        <div className="progress-orbit-wrap"><OrbitGlobe compact /></div>
        <span className="section-index">LIVE ORCHESTRATION</span>
        <h1>Your trip is<br /><em>taking shape.</em></h1>
        <p>
          {activeAgent
            ? `${META[activeAgent].label} is working now. Each specialist hands a structured recommendation to the final orchestrator.`
            : 'Connecting the team and preparing your brief.'}
        </p>
        <div className="progress-meter">
          <div className="progress-meter-label"><span>{percentage}% composed</span><span>{doneCount} of {agents.length}</span></div>
          <div className="progress-track"><span style={{ width: `${percentage}%` }} /></div>
        </div>
      </div>

      <div className="agent-board">
        <div className="agent-board-head">
          <div>
            <span className="section-index">AGENT ROOM</span>
            <h2>Working session</h2>
          </div>
          <span className="live-badge"><span className="live-pulse" /> Live</span>
        </div>

        <ol className="agent-list">
          {agents.map((agent, index) => {
            const status = statuses[agent] || 'pending'
            const { label, note, icon: AgentIcon } = META[agent]
            return (
              <li key={agent} className={`agent-row ${status}`}>
                <span className="agent-number">{String(index + 1).padStart(2, '0')}</span>
                <span className="agent-icon"><AgentIcon size={19} strokeWidth={1.8} /></span>
                <span className="agent-copy"><strong>{label}</strong><small>{note}</small></span>
                <span className="agent-state">
                  {status === 'done' && <><Check size={15} /> Complete</>}
                  {status === 'running' && <><LoaderCircle className="spinner" size={15} /> Thinking</>}
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
