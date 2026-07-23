import { useCallback, useRef, useState } from 'react'
import {
  ArrowLeft,
  BedDouble,
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
  RefreshCw,
} from 'lucide-react'
import { streamPlan } from './api.js'
import InputForm from './components/InputForm.jsx'
import ProgressTracker from './components/ProgressTracker.jsx'
import ItineraryView from './components/ItineraryView.jsx'
import MapView from './components/MapView.jsx'
import BudgetView from './components/BudgetView.jsx'
import PackingList from './components/PackingList.jsx'
import ReasoningLog from './components/ReasoningLog.jsx'
import BookingPanel from './components/BookingPanel.jsx'
import OrbitGlobe from './components/OrbitGlobe.jsx'
import AccessibilityButton from './components/accessibility/AccessibilityButton.jsx'
import AccessibilityPanel from './components/accessibility/AccessibilityPanel.jsx'

const AGENTS = ['budget', 'transportation', 'housing', 'food', 'activity', 'planning', 'orchestrator']

const TABS = [
  { id: 'itinerary', label: 'Itinerary', icon: Route },
  { id: 'map', label: 'Places', icon: Map },
  { id: 'budget', label: 'Budget', icon: CircleDollarSign },
  { id: 'stay', label: 'Book stay', icon: BedDouble },
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

function AppHeader({ step, onReset, onAccessibility, accessibilityButtonRef }) {
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
        <AccessibilityButton onClick={onAccessibility} buttonRef={accessibilityButtonRef} />
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
  const [reviewData, setReviewData] = useState(null)
  const [adjustedBudget, setAdjustedBudget] = useState(null)
  const [error, setError] = useState(null)
  const [tab, setTab] = useState('itinerary')
  const [tripInput, setTripInput] = useState(null)
  const [accessibilityOpen, setAccessibilityOpen] = useState(false)
  const accessibilityButtonRef = useRef(null)

  async function handleSubmit(input) {
    setError(null)
    setResult(null)
    setReviewData(null)
    setAdjustedBudget(null)
    setTripInput(input)
    setStatuses(Object.fromEntries(AGENTS.map((agent) => [agent, 'pending'])))
    setStep('progress')
    window.scrollTo({ top: 0, behavior: 'smooth' })

    try {
      await streamPlan(input, (event) => {
        if (event.type === 'agent_start') {
          setStatuses((current) => ({ ...current, [event.agent]: 'running' }))
        } else if (event.type === 'agent_done') {
          setStatuses((current) => ({ ...current, [event.agent]: 'done' }))
          // Capture agent outputs as they arrive for review
          if (event.output) {
            setReviewData((prev) => ({
              ...prev,
              agent_outputs: { ...(prev?.agent_outputs || {}), [event.agent]: event.output },
            }))
          }
        } else if (event.type === 'complete') {
          setResult(event.result)
          setReviewData(event.result)
          setTab('itinerary')
          setStep('review')  // Show review/confirmation before final result
        } else if (event.type === 'error') {
          setError(event.message)
        }
      })
    } catch (requestError) {
      setError(requestError.message)
    }
  }

  const handleConfirmAndFinalize = useCallback(async () => {
    if (!tripInput || !result) return
    if (!adjustedBudget) {
      setTab('itinerary')
      setStep('result')
      return
    }
    setStep('progress')
    setError(null)

    try {
      const res = await fetch(`${import.meta.env.VITE_API_BASE || 'http://localhost:8000'}/plan/finalize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          trip: tripInput,
          adjusted_budget: adjustedBudget || undefined,
        }),
      })
      if (!res.ok) throw new Error(`Finalize failed: ${res.status}`)
      const data = await res.json()
      setResult(data)
      setTab('itinerary')
      setStep('result')
    } catch (e) {
      setError(e.message)
    }
  }, [tripInput, result, adjustedBudget])

  function reset() {
    setStep('input')
    setResult(null)
    setReviewData(null)
    setAdjustedBudget(null)
    setError(null)
    setTab('itinerary')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return (
    <div className={`app-shell view-${step}`}>
      <AppHeader
        step={step}
        onReset={reset}
        onAccessibility={() => setAccessibilityOpen(true)}
        accessibilityButtonRef={accessibilityButtonRef}
      />
      <AccessibilityPanel
        open={accessibilityOpen}
        onClose={() => setAccessibilityOpen(false)}
        returnFocusRef={accessibilityButtonRef}
      />

      {step === 'input' && <Landing onSubmit={handleSubmit} />}

      {step === 'progress' && (
        <main className="progress-page">
          <ProgressTracker agents={AGENTS} statuses={statuses} error={error} onRetry={reset} />
        </main>
      )}

      {step === 'review' && result && (
        <main className="result-page">
          <ResultHeader result={result} />

          <section className="review-confirm-banner">
            <div className="review-confirm-content">
              <div>
                <span className="section-index">REVIEW & CONFIRM</span>
                <h2>Your trip plan is ready for review</h2>
                <p>
                  All 6 agents have completed their research with real-time data from Ctrip, Numbeo,
                  and weather services. Review the budget allocation below — drag the sliders to
                  adjust spending priorities, then confirm to finalize your itinerary.
                </p>
              </div>
              <div className="review-actions">
                <button className="primary-button" onClick={handleConfirmAndFinalize}>
                  <Check size={18} /> Confirm & finalize
                </button>
                <button className="text-button" onClick={reset}>
                  <RefreshCw size={16} /> Start over
                </button>
              </div>
            </div>
          </section>

          <BudgetView
            cost={result.cost}
            budgetAgent={result.agent_outputs?.budget}
            onBudgetChange={setAdjustedBudget}
          />

          <section className="review-summary" style={{ padding: '32px', maxWidth: 900, margin: '0 auto' }}>
            <div className="panel-heading">
              <div><span className="section-index">PREVIEW</span><h2>Day-by-day itinerary preview</h2></div>
            </div>
            <ItineraryView result={result} />
          </section>
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
            {tab === 'map' && (
              <MapView
                points={result.map_points}
                result={result}
                agentOutputs={result.agent_outputs}
              />
            )}
            {tab === 'stay' && tripInput && <BookingPanel trip={tripInput} />}
            {tab === 'budget' && (
              <BudgetView
                cost={result.cost}
                budgetAgent={result.agent_outputs.budget}
                onBudgetChange={setAdjustedBudget}
              />
            )}
            {tab === 'packing' && (
              <PackingList
                items={result.packing_list}
                weather={result.weather_summary}
                pacing={result.agent_outputs.planning.pacing_notes}
                dailyWeather={result.agent_outputs.planning.daily_weather}
                healthAdvice={result.agent_outputs.planning.health_advice}
                tripId={result.trip_id}
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
