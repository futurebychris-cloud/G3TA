import { useState } from 'react'
import {
  ArrowLeft,
  BrainCircuit,
  CalendarDays,
  Check,
  CircleDollarSign,
  Compass,
  ListChecks,
  Luggage,
  Map,
  Menu,
  Route,
  ShieldAlert,
  Sparkles,
} from 'lucide-react'
import { streamPlan } from './api.js'
import InputForm from './components/InputForm.jsx'
import ProgressTracker from './components/ProgressTracker.jsx'
import ItineraryView from './components/ItineraryView.jsx'
import MapView from './components/MapView.jsx'
import BudgetView from './components/BudgetView.jsx'
import PackingList from './components/PackingList.jsx'
import ReasoningLog from './components/ReasoningLog.jsx'
import OrbitGlobe from './components/OrbitGlobe.jsx'

const AGENTS = ['budget', 'transportation', 'housing', 'food', 'activity', 'planning', 'orchestrator']

const TABS = [
  { id: 'itinerary', label: 'Itinerary', icon: Route },
  { id: 'map', label: 'Places', icon: Map },
  { id: 'budget', label: 'Budget', icon: CircleDollarSign },
  { id: 'packing', label: 'Packing', icon: Luggage },
  { id: 'reasoning', label: 'Agent log', icon: ListChecks },
]

function Brand() {
  return (
    <div className="brand" aria-label="G3TA home">
      <span className="brand-mark"><Compass size={19} strokeWidth={2.2} /></span>
      <span className="brand-word">G3TA</span>
      <span className="brand-divider" />
      <span className="brand-sub">Journey intelligence</span>
    </div>
  )
}

function AppHeader({ step, onReset }) {
  return (
    <header className="site-header">
      <button className="brand-button" type="button" onClick={step === 'input' ? undefined : onReset}>
        <Brand />
      </button>
      <div className="header-actions">
        <span className="system-status"><span className="status-light" /> DeepSeek online</span>
        {step !== 'input' && (
          <button className="text-button" onClick={onReset}>
            <ArrowLeft size={16} /> New journey
          </button>
        )}
        <button className="menu-button" type="button" aria-label="Open menu"><Menu size={20} /></button>
      </div>
    </header>
  )
}

function Landing({ onSubmit }) {
  return (
    <main className="landing">
      <section className="hero">
        <div className="hero-copy">
          <div className="eyebrow"><Sparkles size={15} /> Multi-agent trip design</div>
          <h1>
            The world is wide.
            <span>Plan it beautifully.</span>
          </h1>
          <p className="hero-lede">
            Tell us where you want to go. Six specialist agents research the details,
            challenge the trade-offs, and shape one thoughtful itinerary around you.
          </p>
          <div className="hero-proof">
            <div><strong>06</strong><span>Specialist agents</span></div>
            <div><strong>01</strong><span>Coordinated plan</span></div>
            <div><strong>100%</strong><span>Visible reasoning</span></div>
          </div>
        </div>
        <div className="hero-visual">
          <OrbitGlobe />
        </div>
      </section>

      <section className="planner-wrap" id="plan">
        <div className="planner-heading">
          <div>
            <span className="section-index">01 / START</span>
            <h2>Where to next?</h2>
          </div>
          <p>Start with the essentials. Fine-tune the flavor below.</p>
        </div>
        <InputForm onSubmit={onSubmit} />
      </section>

      <section className="method-strip" aria-label="How it works">
        <div className="method-intro">
          <span className="section-index">THE ENSEMBLE</span>
          <h2>One journey.<br />Many points of view.</h2>
        </div>
        <div className="method-step">
          <span>01</span><BrainCircuit size={22} />
          <h3>Six minds explore</h3>
          <p>Specialists independently handle routes, stays, food, experiences, pacing, and cost.</p>
        </div>
        <div className="method-step">
          <span>02</span><CircleDollarSign size={22} />
          <h3>Trade-offs get tested</h3>
          <p>The orchestrator checks the whole plan against your budget and records every adjustment.</p>
        </div>
        <div className="method-step">
          <span>03</span><Check size={22} />
          <h3>You get one clear plan</h3>
          <p>A coherent day-by-day itinerary, with every useful detail in one calm workspace.</p>
        </div>
      </section>
    </main>
  )
}

function ResultHeader({ result }) {
  const start = new Date(`${result.dates.start}T00:00:00`)
  const end = new Date(`${result.dates.end}T00:00:00`)
  const duration = Math.max(1, Math.round((end - start) / 86400000) + 1)
  const dateLabel = `${start.toLocaleDateString('en', { month: 'short', day: 'numeric' })} — ${end.toLocaleDateString('en', { month: 'short', day: 'numeric', year: 'numeric' })}`

  return (
    <section className="trip-masthead">
      <div className="trip-kicker"><span className="status-light" /> Your journey is ready</div>
      <div className="trip-title-row">
        <div>
          <span className="section-index">CURATED FOR YOU</span>
          <h1>{result.destination}</h1>
        </div>
        <div className="trip-stamp" aria-hidden="true"><span>G3</span><small>PLANNED<br />WITH AI</small></div>
      </div>
      <p className="trip-summary">{result.summary}</p>
      <div className="trip-facts">
        <div><CalendarDays size={18} /><span><small>DATES</small>{dateLabel}</span></div>
        <div><Route size={18} /><span><small>DURATION</small>{duration} days</span></div>
        <div><CircleDollarSign size={18} /><span><small>ESTIMATED</small>{result.cost.currency} {result.cost.total.toLocaleString()}</span></div>
        <div><Check size={18} /><span><small>STATUS</small>{result.cost.within_budget ? 'Within budget' : 'Needs review'}</span></div>
      </div>
      {result.verification_notice && (
        <div className="verification-banner">
          <ShieldAlert size={18} />
          <span><strong>Planning estimate</strong>{result.verification_notice}</span>
        </div>
      )}
    </section>
  )
}

export default function App() {
  const [step, setStep] = useState('input')
  const [statuses, setStatuses] = useState({})
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [tab, setTab] = useState('itinerary')

  async function handleSubmit(tripInput) {
    setError(null)
    setResult(null)
    setStatuses(Object.fromEntries(AGENTS.map((agent) => [agent, 'pending'])))
    setStep('progress')
    window.scrollTo({ top: 0, behavior: 'smooth' })

    try {
      await streamPlan(tripInput, (event) => {
        if (event.type === 'agent_start') {
          setStatuses((current) => ({ ...current, [event.agent]: 'running' }))
        } else if (event.type === 'agent_done') {
          setStatuses((current) => ({ ...current, [event.agent]: 'done' }))
        } else if (event.type === 'complete') {
          setResult(event.result)
          setTab('itinerary')
          setStep('result')
        } else if (event.type === 'error') {
          setError(event.message)
        }
      })
    } catch (requestError) {
      setError(requestError.message)
    }
  }

  function reset() {
    setStep('input')
    setResult(null)
    setError(null)
    setTab('itinerary')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <div className={`app-shell view-${step}`}>
      <AppHeader step={step} onReset={reset} />

      {step === 'input' && <Landing onSubmit={handleSubmit} />}

      {step === 'progress' && (
        <main className="progress-page">
          <ProgressTracker agents={AGENTS} statuses={statuses} error={error} onRetry={reset} />
        </main>
      )}

      {step === 'result' && result && (
        <main className="result-page">
          <ResultHeader result={result} />

          <nav className="result-tabs" aria-label="Trip details">
            {TABS.map(({ id, label, icon: Icon }) => (
              <button key={id} className={tab === id ? 'result-tab active' : 'result-tab'} onClick={() => setTab(id)}>
                <Icon size={17} strokeWidth={1.8} />
                {label}
              </button>
            ))}
          </nav>

          <section className="result-panel">
            {tab === 'itinerary' && <ItineraryView result={result} />}
            {tab === 'map' && <MapView points={result.map_points} />}
            {tab === 'budget' && <BudgetView cost={result.cost} budgetAgent={result.agent_outputs.budget} />}
            {tab === 'packing' && (
              <PackingList
                items={result.packing_list}
                weather={result.weather_summary}
                pacing={result.agent_outputs.planning.pacing_notes}
              />
            )}
            {tab === 'reasoning' && <ReasoningLog log={result.reasoning_log} />}
          </section>
        </main>
      )}

      <footer className="site-footer">
        <Brand />
        <p>Thoughtful journeys, composed by people and machines.</p>
        <span>DeepSeek-powered · G3TA 2026</span>
      </footer>
    </div>
  )
}
