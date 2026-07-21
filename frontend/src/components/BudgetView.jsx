import { AlertTriangle, Check, CircleDollarSign, Gauge } from 'lucide-react'

const LABELS = {
  transportation: 'Getting there',
  housing: 'Places to stay',
  food: 'Food & drink',
  activity: 'Experiences',
  local_transport: 'Getting around',
}

const COLORS = ['#ff6b4a', '#ccf06c', '#80caff', '#b9a4ff', '#ffca6b']

export default function BudgetView({ cost, budgetAgent }) {
  const { breakdown, total, budget, currency, within_budget: withinBudget } = cost
  const entries = Object.entries(breakdown)
  const maximum = Math.max(...Object.values(breakdown), 1)
  const usedPercentage = Math.round((total / Math.max(budget, 1)) * 100)
  const remaining = Math.max(budget - total, 0)
  let runningAngle = 0
  const gradient = entries.map(([, value], index) => {
    const start = runningAngle
    runningAngle += (value / Math.max(total, 1)) * 360
    return `${COLORS[index]} ${start}deg ${runningAngle}deg`
  }).join(', ')

  return (
    <div className="budget-view">
      <div className="panel-heading">
        <div><span className="section-index">MONEY, CONSIDERED</span><h2>A clear view of<br />where it all goes.</h2></div>
        <p>The orchestrator checked every recommendation together—not as isolated estimates.</p>
      </div>

      <div className="budget-overview">
        <div className="budget-ring-card">
          <div className="budget-ring" style={{ background: `conic-gradient(${gradient})` }}>
            <div><small>ESTIMATED TOTAL</small><strong>{currency} {total.toLocaleString()}</strong><span>of {budget.toLocaleString()}</span></div>
          </div>
          <span className={withinBudget ? 'budget-status positive' : 'budget-status negative'}>
            {withinBudget ? <Check size={15} /> : <AlertTriangle size={15} />}
            {withinBudget ? `${currency} ${remaining.toLocaleString()} remains` : `${usedPercentage}% of budget`}
          </span>
        </div>

        <div className="budget-breakdown">
          <div className="budget-breakdown-head"><h3>Cost breakdown</h3><span>{usedPercentage}% used</span></div>
          {entries.map(([key, value], index) => (
            <div className="budget-line" key={key}>
              <span className="budget-swatch" style={{ background: COLORS[index] }} />
              <span className="budget-line-label"><strong>{LABELS[key] || key}</strong><small>{Math.round((value / Math.max(total, 1)) * 100)}% of trip</small></span>
              <span className="budget-bar"><i style={{ width: `${(value / maximum) * 100}%`, background: COLORS[index] }} /></span>
              <strong className="budget-amount">{currency} {value.toLocaleString()}</strong>
            </div>
          ))}
        </div>
      </div>

      <div className="budget-detail-grid">
        {budgetAgent?.daily_caps && (
          <section className="daily-caps-card">
            <div className="detail-card-icon"><Gauge size={20} /></div>
            <div><span className="section-index">DAILY GUARDRAILS</span><h3>Budget agent guidance</h3></div>
            <div className="cap-grid">
              {Object.entries(budgetAgent.daily_caps).map(([key, value]) => (
                <div key={key}><span>{LABELS[key] || key}</span><strong>{currency} {Math.round(value)}</strong><small>/ day</small></div>
              ))}
            </div>
          </section>
        )}

        <section className="budget-note-card">
          <div className="detail-card-icon"><CircleDollarSign size={20} /></div>
          <div><span className="section-index">AGENT NOTES</span><h3>{budgetAgent?.warnings?.length ? 'Worth knowing' : 'Budget looks balanced'}</h3></div>
          {budgetAgent?.warnings?.length ? (
            <ul>{budgetAgent.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>
          ) : (
            <p>No material budget warnings were raised. You still have room for spontaneity.</p>
          )}
        </section>
      </div>
    </div>
  )
}
