// Live agent checklist (PRD §9 step 2). Reflects the SSE stream: each agent goes
// pending → running → done as the backend runs them in order.
const LABELS = {
  budget: 'Budget Agent',
  transportation: 'Transportation Agent',
  housing: 'Housing Agent',
  food: 'Food Agent',
  activity: 'Activity Agent',
  planning: 'Planning Agent',
  orchestrator: 'Orchestrator (synthesizing itinerary)',
}

const ICON = { pending: '○', running: '◐', done: '●' }

export default function ProgressTracker({ agents, statuses, error, onRetry }) {
  const doneCount = agents.filter((a) => statuses[a] === 'done').length
  const pct = Math.round((doneCount / agents.length) * 100)

  return (
    <div className="card progress">
      <h2>Planning your trip…</h2>
      <div className="bar">
        <div className="bar-fill" style={{ width: `${pct}%` }} />
      </div>

      <ul className="checklist">
        {agents.map((a) => (
          <li key={a} className={`status-${statuses[a] || 'pending'}`}>
            <span className="dot">{ICON[statuses[a]] || ICON.pending}</span>
            {LABELS[a]}
          </li>
        ))}
      </ul>

      {error && (
        <div className="error">
          <strong>Something went wrong:</strong>
          <p>{error}</p>
          <button className="ghost" onClick={onRetry}>← Back to form</button>
        </div>
      )}
    </div>
  )
}
