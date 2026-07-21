// Reasoning / objection log — the demo-able proof this is genuinely multi-agent
// (PRD §5 "Why this shape" and §13 step 4). Each entry traces a decision or
// trade-off back to the agent that made it.
export default function ReasoningLog({ log }) {
  if (!log || log.length === 0) {
    return <p className="muted">No reasoning recorded.</p>
  }
  return (
    <div className="reasoning">
      <p className="muted">
        Each specialist agent owns one domain. This log traces which agent made which call —
        including any trade-off the Orchestrator had to force (e.g. a lodging downgrade to fit the budget).
      </p>
      <ul className="reasoning-list">
        {log.map((entry, i) => (
          <li key={i} className={entry.agent === 'Orchestrator' ? 'orchestrator' : ''}>
            <span className="agent-tag">{entry.agent}</span>
            <span className="agent-note">{entry.note}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
