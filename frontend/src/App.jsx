import { useState } from 'react'
import { streamPlan } from './api.js'
import InputForm from './components/InputForm.jsx'
import ProgressTracker from './components/ProgressTracker.jsx'
import ItineraryView from './components/ItineraryView.jsx'
import MapView from './components/MapView.jsx'
import BudgetView from './components/BudgetView.jsx'
import PackingList from './components/PackingList.jsx'
import ReasoningLog from './components/ReasoningLog.jsx'

const AGENTS = ['budget', 'transportation', 'housing', 'food', 'activity', 'planning', 'orchestrator']

export default function App() {
  const [step, setStep] = useState('input') // input | progress | result
  const [statuses, setStatuses] = useState({})
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [tab, setTab] = useState('itinerary')

  async function handleSubmit(tripInput) {
    setError(null)
    setResult(null)
    setStatuses(Object.fromEntries(AGENTS.map((a) => [a, 'pending'])))
    setStep('progress')

    try {
      await streamPlan(tripInput, (evt) => {
        if (evt.type === 'agent_start') {
          setStatuses((s) => ({ ...s, [evt.agent]: 'running' }))
        } else if (evt.type === 'agent_done') {
          setStatuses((s) => ({ ...s, [evt.agent]: 'done' }))
        } else if (evt.type === 'complete') {
          setResult(evt.result)
          setStep('result')
        } else if (evt.type === 'error') {
          setError(evt.message)
        }
      })
    } catch (e) {
      setError(e.message)
    }
  }

  function reset() {
    setStep('input')
    setResult(null)
    setError(null)
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>🧭 Multi-Agent AI Trip Planner</h1>
        <p className="subtitle">Six specialist agents + an orchestrator, coordinated into one itinerary.</p>
      </header>

      {step === 'input' && <InputForm onSubmit={handleSubmit} />}

      {step === 'progress' && (
        <ProgressTracker agents={AGENTS} statuses={statuses} error={error} onRetry={reset} />
      )}

      {step === 'result' && result && (
        <div className="result">
          <div className="result-toolbar">
            <button className="ghost" onClick={reset}>← Plan another trip</button>
            <div className="result-title">
              {result.destination} · {result.dates.start} → {result.dates.end}
            </div>
          </div>

          <nav className="tabs">
            {['itinerary', 'map', 'budget', 'packing', 'reasoning'].map((t) => (
              <button key={t} className={tab === t ? 'tab active' : 'tab'} onClick={() => setTab(t)}>
                {t[0].toUpperCase() + t.slice(1)}
              </button>
            ))}
          </nav>

          <section className="tab-panel">
            {tab === 'itinerary' && <ItineraryView result={result} />}
            {tab === 'map' && <MapView points={result.map_points} />}
            {tab === 'budget' && <BudgetView cost={result.cost} budgetAgent={result.agent_outputs.budget} />}
            {tab === 'packing' && (
              <PackingList items={result.packing_list} weather={result.weather_summary} pacing={result.agent_outputs.planning.pacing_notes} />
            )}
            {tab === 'reasoning' && <ReasoningLog log={result.reasoning_log} />}
          </section>
        </div>
      )}
    </div>
  )
}
