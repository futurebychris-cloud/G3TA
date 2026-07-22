import { useState } from 'react'
import { BrainCircuit, CheckCircle2, GitCompareArrows, ScanSearch } from 'lucide-react'
import { useAccessibilitySettings } from '../accessibility/AccessibilityContext.jsx'
import LineFocusReader from './accessibility/LineFocusReader.jsx'
import ReadAloudButton from './accessibility/ReadAloudButton.jsx'

const AGENT_ICONS = {
  Orchestrator: GitCompareArrows,
  Budget: ScanSearch,
}

export default function ReasoningLog({ log }) {
  const { settings } = useAccessibilitySettings()
  const [showAll, setShowAll] = useState(false)
  const isSenior = settings.preset === 'senior'
  if (!log || log.length === 0) {
    return <div className="empty-state"><BrainCircuit size={28} /><h3>No agent notes yet</h3><p>Reasoning will appear when the team records its decisions.</p></div>
  }

  return (
    <div className="reasoning-view">
      <div className="panel-heading">
        <div><span className="section-index">BEHIND THE PLAN</span><h2>Every decision<br />has a reason.</h2></div>
        <p>This is the handoff trail: what each specialist proposed and which trade-offs the orchestrator made.</p>
      </div>
      <div className="result-heading-actions">
        <ReadAloudButton id="agent-reasoning" label="agent decision log" text={log.flatMap((entry) => [entry.agent, entry.note])} />
      </div>

      <div className="reasoning-intro">
        <div className="reasoning-mark" aria-hidden="true"><BrainCircuit size={28} /></div>
        <div><span className="section-index">TRANSPARENT BY DESIGN</span><h3>Not a black box.</h3><LineFocusReader text="Six domain agents reason independently. The orchestrator then checks their combined work and resolves conflicts before the final schedule is written." /></div>
      </div>

      <ol className="reasoning-trail">
        {(isSenior && !showAll ? log.slice(0, 3) : log).map((entry, index) => {
          const Icon = AGENT_ICONS[entry.agent] || CheckCircle2
          return (
            <li key={`${entry.agent}-${index}`} className={entry.agent === 'Orchestrator' ? 'orchestrator-note' : ''}>
              <div className="reasoning-node" aria-hidden="true"><Icon size={18} /></div>
              <div className="reasoning-entry">
                <div><span>{entry.agent}</span><small>Decision {String(index + 1).padStart(2, '0')}</small></div>
                <LineFocusReader text={entry.note} />
              </div>
            </li>
          )
        })}
      </ol>
      {isSenior && log.length > 3 && (
        <button className="show-more-results" type="button" aria-expanded={showAll} onClick={() => setShowAll((current) => !current)}>
          {showAll ? 'Show fewer decisions' : `Show all ${log.length} decisions`}
        </button>
      )}
    </div>
  )
}
