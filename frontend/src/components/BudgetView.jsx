import { AlertTriangle, Check, CircleDollarSign, Gauge, TrendingUp, Receipt } from 'lucide-react'
import ReadAloudButton from './accessibility/ReadAloudButton.jsx'

const LABELS = {
  transportation: 'Getting there',
  housing: 'Places to stay',
  food: 'Food & drink',
  activity: 'Experiences',
  local_transport: 'Getting around',
  other: 'Other',
}

const DEFAULT_COLORS = ['#ff6b4a', '#ccf06c', '#80caff', '#b9a4ff', '#ffca6b']

function colorForKey(key) {
  const map = {
    transportation: '#FF6384', housing: '#36A2EB', food: '#FFCE56',
    activity: '#4BC0C0', other: '#9966FF', local_transport: '#FF9F40',
  }
  return map[key] || DEFAULT_COLORS[0]
}

export default function BudgetView({ cost, budgetAgent }) {
  const { breakdown, total, budget, currency, within_budget: withinBudget, expense_items: expenseItems } = cost
  const entries = Object.entries(breakdown).filter(([, v]) => v > 0)
  const maximum = Math.max(...Object.values(breakdown).filter(v => v > 0), 1)
  const usedPercentage = Math.round((total / Math.max(budget, 1)) * 100)
  const remaining = Math.max(budget - total, 0)

  // Ring chart ALWAYS uses ACTUAL cost proportions from agent data
  let runningAngle = 0
  const gradient = entries
    .map(([key, value]) => {
      const color = colorForKey(key)
      const start = runningAngle
      runningAngle += (value / Math.max(total, 1)) * 360
      return `${color} ${start}deg ${runningAngle}deg`
    }).join(', ')

  const spokenBudget = [
    withinBudget
      ? `Total estimated cost: ${currency} ${total.toLocaleString()}, ${currency} ${remaining.toLocaleString()} remains of your ${currency} ${budget.toLocaleString()} budget.`
      : `Total estimated cost: ${currency} ${total.toLocaleString()}, ${usedPercentage}% of your ${currency} ${budget.toLocaleString()} budget.`,
    ...entries.map(([key, value]) => (
      `${LABELS[key] || key}: ${currency} ${value.toLocaleString()}, ${Math.round((value / Math.max(total, 1)) * 100)}% of the trip.`
    )),
    ...(budgetAgent?.warnings || []),
  ]

  return (
    <div className="budget-view">
      <div className="panel-heading">
        <div><span className="section-index">MONEY, CONSIDERED</span><h2>A clear view of<br />where it all goes.</h2></div>
        <p>Real agent costs reconciled against your total budget — every line item is based on actual search results.</p>
      </div>
      <div className="result-heading-actions">
        <ReadAloudButton id="budget-breakdown" label="the budget breakdown" text={spokenBudget} />
      </div>

      <div className="budget-overview">
        <div className="budget-ring-card">
          <div className="budget-ring" style={{ background: `conic-gradient(${gradient})` }}>
            <div><small>ESTIMATED TOTAL</small><strong>{currency} {total.toLocaleString()}</strong><span>of {budget.toLocaleString()}</span></div>
          </div>
          <span className={withinBudget ? 'budget-status positive' : 'budget-status negative'}>
            {withinBudget ? <Check size={15} /> : <AlertTriangle size={15} />}
            {withinBudget
              ? `${currency} ${remaining.toLocaleString()} remains`
              : usedPercentage > 200
                ? `${usedPercentage}% used — significantly over`
                : `${usedPercentage}% used`
            }
          </span>
        </div>

        <div className="budget-breakdown">
          <div className="budget-breakdown-head">
            <h3>Cost breakdown</h3>
            <span className={withinBudget ? '' : 'over-budget'}>{usedPercentage}% used</span>
          </div>
          {entries.map(([key, value], index) => (
            <div className="budget-line" key={key}>
              <span className="budget-swatch" style={{ background: colorForKey(key) }} />
              <span className="budget-line-label">
                <strong>{LABELS[key] || key}</strong>
                <small>{Math.round((value / Math.max(total, 1)) * 100)}% of trip</small>
              </span>
              <span className="budget-bar"><i style={{ width: `${Math.min((value / Math.max(maximum, 1)) * 100, 100)}%`, background: colorForKey(key) }} /></span>
              <strong className="budget-amount">{currency} {value.toLocaleString()}</strong>
            </div>
          ))}
        </div>
      </div>

      {/* Expense line items — real itemized costs from each agent */}
      {expenseItems && expenseItems.length > 0 && (
        <div className="budget-overview" style={{ marginTop: 0 }}>
          <div className="budget-breakdown" style={{ width: '100%' }}>
            <div className="budget-breakdown-head">
              <h3><Receipt size={16} style={{ display: 'inline', marginRight: 6, verticalAlign: -2 }} />Expense details</h3>
            </div>
            {expenseItems.map((item, idx) => (
              <div className="budget-line" key={idx}>
                <span className="budget-swatch" style={{ background: colorForKey(item.category) }} />
                <span className="budget-line-label">
                  <strong>{item.label}</strong>
                  <small>{item.detail}</small>
                </span>
                <strong className="budget-amount" style={{ marginLeft: 'auto' }}>
                  {item.currency} {item.amount.toLocaleString()}
                </strong>
              </div>
            ))}
            <div className="budget-line" style={{ borderTop: '1px solid #e5e7eb', paddingTop: 10, marginTop: 4 }}>
              <span className="budget-line-label"><strong>Total</strong></span>
              <strong className="budget-amount" style={{ marginLeft: 'auto' }}>
                {currency} {total.toLocaleString()}
              </strong>
            </div>
          </div>
        </div>
      )}

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

        {budgetAgent?.web_search_costs && Object.keys(budgetAgent.web_search_costs).length > 0 && (
          <section className="daily-caps-card">
            <div className="detail-card-icon"><TrendingUp size={20} /></div>
            <div><span className="section-index">REAL MARKET DATA</span><h3>Web-scraped destination costs</h3></div>
            <div className="cap-grid">
              {Object.entries(budgetAgent.web_search_costs).map(([key, value]) => (
                <div key={key}><span>{key}</span><strong>{currency} {Math.round(value)}</strong><small>/ day avg</small></div>
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
