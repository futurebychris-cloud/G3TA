// Budget breakdown (PRD §9 step 3). Shows the reconciled cost vs. budget plus the
// Budget Agent's per-category daily caps and warnings.
const LABELS = {
  transportation: 'Transportation',
  housing: 'Housing',
  food: 'Food',
  activity: 'Activities',
  local_transport: 'Local transport',
}

export default function BudgetView({ cost, budgetAgent }) {
  const { breakdown, total, budget, currency, within_budget } = cost
  const max = Math.max(...Object.values(breakdown), 1)

  return (
    <div className="budget">
      <div className="budget-summary">
        <div>
          <span className="big">{currency} {total.toLocaleString()}</span>
          <span className="muted"> / {budget.toLocaleString()} budget</span>
        </div>
        <span className={within_budget ? 'badge ok' : 'badge over'}>
          {within_budget ? '✓ Within budget' : '✗ Over budget'}
        </span>
      </div>

      <div className="bars">
        {Object.entries(breakdown).map(([k, v]) => (
          <div key={k} className="bar-row">
            <span className="bar-label">{LABELS[k] || k}</span>
            <div className="bar-track">
              <div className="bar-value" style={{ width: `${(v / max) * 100}%` }} />
            </div>
            <span className="bar-amount">{currency} {v.toLocaleString()}</span>
          </div>
        ))}
      </div>

      {budgetAgent?.daily_caps && (
        <div className="caps">
          <h4>Budget Agent — daily caps</h4>
          <ul>
            {Object.entries(budgetAgent.daily_caps).map(([k, v]) => (
              <li key={k}>{LABELS[k] || k}: <strong>{currency} {Math.round(v)}/day</strong></li>
            ))}
          </ul>
        </div>
      )}

      {budgetAgent?.warnings?.length > 0 && (
        <div className="warnings">
          <h4>⚠ Warnings</h4>
          <ul>{budgetAgent.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
        </div>
      )}
    </div>
  )
}
