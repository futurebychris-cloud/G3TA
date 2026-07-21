import { BrainCircuit, CheckCircle2, GitCompareArrows, ScanSearch } from 'lucide-react'

const AGENT_ICONS = {
  Orchestrator: GitCompareArrows,
  Budget: ScanSearch,
}

export default function ReasoningLog({ log }) {
  if (!log || log.length === 0) {
    return <div className="empty-state"><BrainCircuit size={28} /><h3>No agent notes yet</h3><p>Reasoning will appear when the team records its decisions.</p></div>
  }

  return (
    <div className="reasoning-view">
      <div className="panel-heading">
        <div><span className="section-index">BEHIND THE PLAN</span><h2>Every decision<br />has a reason.</h2></div>
        <p>This is the handoff trail: what each specialist proposed and which trade-offs the orchestrator made.</p>
      </div>

      <div className="reasoning-intro">
        <div className="reasoning-mark"><BrainCircuit size={28} /></div>
        <div><span className="section-index">TRANSPARENT BY DESIGN</span><h3>Not a black box.</h3><p>Six domain agents reason independently. The orchestrator then checks their combined work and resolves conflicts before the final schedule is written.</p></div>
      </div>

      <ol className="reasoning-trail">
        {log.map((entry, index) => {
          const Icon = AGENT_ICONS[entry.agent] || CheckCircle2
          return (
            <li key={`${entry.agent}-${index}`} className={entry.agent === 'Orchestrator' ? 'orchestrator-note' : ''}>
              <div className="reasoning-node"><Icon size={18} /></div>
              <div className="reasoning-entry">
                <div><span>{entry.agent}</span><small>Decision {String(index + 1).padStart(2, '0')}</small></div>
                <p>{entry.note}</p>
              </div>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
