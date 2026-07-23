import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ArrowLeft,
  BedDouble,
  CalendarDays,
  Check,
  CircleDollarSign,
  Compass,
  Luggage,
  Map,
  Menu,
  Route,
  ShieldAlert,
  Sparkles,
} from 'lucide-react'
import { cancelPlan, finalizePlan, getHealth, loadLatestResult, saveResult, streamPlan } from './api.js'
import { getCookie, setCookie } from './utils/cookie.js'
import { useAccessibilitySettings } from './accessibility/AccessibilityContext.jsx'
import InputForm from './components/InputForm.jsx'
import ProgressTracker from './components/ProgressTracker.jsx'
import ItineraryView from './components/ItineraryView.jsx'
import MapView from './components/MapView.jsx'
import BudgetView from './components/BudgetView.jsx'
import PackingList from './components/PackingList.jsx'
import BookingPanel from './components/BookingPanel.jsx'
import OrbitGlobe from './components/OrbitGlobe.jsx'
import AccessibilityButton from './components/accessibility/AccessibilityButton.jsx'
import AccessibilityPanel from './components/accessibility/AccessibilityPanel.jsx'
import ConfirmationDialog from './components/accessibility/ConfirmationDialog.jsx'
import EmergencyInformation from './components/accessibility/EmergencyInformation.jsx'
import NextStepHelper from './components/accessibility/NextStepHelper.jsx'

const AGENTS = ['transportation', 'budget', 'activity', 'housing', 'food', 'planning', 'orchestrator']

const TABS = [
  { id: 'itinerary', label: 'Itinerary', icon: Route },
  { id: 'map', label: 'Places', icon: Map },
  { id: 'budget', label: 'Budget', icon: CircleDollarSign },
  { id: 'stay', label: 'Compare stays', icon: BedDouble },
  { id: 'packing', label: 'Packing', icon: Luggage },
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

function SystemStatus() {
  const [health, setHealth] = useState(null)
  const [unreachable, setUnreachable] = useState(false)

  useEffect(() => {
    let active = true
    getHealth()
      .then((value) => {
        if (active) setHealth(value)
      })
      .catch(() => {
        if (active) setUnreachable(true)
      })
    return () => { active = false }
  }, [])

  const ready = health?.status === 'ok'
  const label = unreachable
    ? 'Backend unavailable'
    : health
      ? ready ? 'Planner ready' : 'Setup needed'
      : 'Checking services'
  return (
    <span className={`system-status${ready ? '' : ' degraded'}`} title={health?.dependencies?.deepseek || ''}>
      <span className="status-light" /> {label}
    </span>
  )
}

function AppHeader({ step, onReset, onAccessibility, accessibilityButtonRef }) {
  return (
    <header className="site-header">
      <button className="brand-button" type="button" onClick={step === 'input' ? undefined : onReset}>
        <Brand />
      </button>
      <div className="header-actions">
        <SystemStatus />
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

function Landing({ onSubmit, savedPlan, onViewSaved }) {
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
            <div><strong>100%</strong><span>Visible progress</span></div>
          </div>
        </div>
        <div className="hero-visual">
          <OrbitGlobe />
        </div>
      </section>

      {savedPlan?.result && (
        <section className="saved-plan-callout" aria-label="Saved plan">
          <div>
            <span className="section-index">SAVED PLAN</span>
            <h3>{savedPlan.result.destination || 'Your last plan'}</h3>
            <p>
              {savedPlan.saved_at ? `Saved ${savedPlan.saved_at}. ` : ''}
              Reopen it without regenerating, or start a fresh journey below.
            </p>
          </div>
          <div className="saved-plan-actions">
            <button type="button" className="primary-button" onClick={onViewSaved}>
              View previous plan
            </button>
          </div>
        </section>
      )}

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

    </main>
  )
}

function ResultHeader({ result }) {
  const start = new Date(`${result.dates.start}T00:00:00`)
  const end = new Date(`${result.dates.end}T00:00:00`)
  const duration = Math.max(1, Math.round((end - start) / 86400000) + 1)
  const dateLabel = `${start.toLocaleDateString('en', { month: 'short', day: 'numeric' })} — ${end.toLocaleDateString('en', { month: 'short', day: 'numeric', year: 'numeric' })}`
  const provenance = result.data_provenance || {}
  const liveSources = provenance.live_sources || []
  const estimatedSources = provenance.estimated_or_unverified_sources || []
  const deepSeekAssisted = result.synthesis_source === 'deepseek_assisted'

  return (
    <section className="trip-masthead">
      <div className="trip-kicker"><span className="status-light" /> Your journey is ready</div>
      <div className="trip-title-row">
        <div>
          <span className="section-index">CURATED FOR YOU</span>
          <h1>{result.destination}</h1>
        </div>
        <div
          className="trip-stamp"
          aria-label={deepSeekAssisted
            ? 'Plan summary assisted by DeepSeek; schedule rule checked'
            : 'Plan generated and rule checked deterministically'}
        >
          <span aria-hidden="true">G3</span>
          <small aria-hidden="true">PLANNED<br />{deepSeekAssisted ? 'AI ASSISTED' : 'RULE CHECKED'}</small>
        </div>
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
          <span>
            <strong>
              {provenance.mode === 'live' ? 'Live provider records'
                : provenance.mode === 'mixed' ? 'Mixed live and estimated data'
                  : 'Planning estimates'}
            </strong>
            {result.verification_notice}
            {(liveSources.length > 0 || estimatedSources.length > 0) && (
              <small className="provenance-detail">
                {liveSources.length > 0 && ` Live: ${liveSources.join(', ')}.`}
                {estimatedSources.length > 0 && ` Estimated or unverified: ${estimatedSources.join(', ')}.`}
              </small>
            )}
          </span>
        </div>
      )}
    </section>
  )
}

export default function App() {
  const { settings } = useAccessibilitySettings()
  const [step, setStep] = useState('input')
  const [statuses, setStatuses] = useState({})
  const [progressEvents, setProgressEvents] = useState([])
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [tab, setTab] = useState('itinerary')
  const [tripInput, setTripInput] = useState(null)
  const [savedPlan, setSavedPlan] = useState(null)
  const [accessibilityOpen, setAccessibilityOpen] = useState(false)
  const [leaveDialogOpen, setLeaveDialogOpen] = useState(false)
  const accessibilityButtonRef = useRef(null)
  const planControllerRef = useRef(null)
  const activeRequestIdRef = useRef(null)

  useEffect(() => () => {
    const requestId = activeRequestIdRef.current
    if (requestId) {
      void cancelPlan(requestId, { keepalive: true }).catch(() => {})
    }
    planControllerRef.current?.abort()
  }, [])

  // Load the cookie-backed saved plan when returning to the landing screen so
  // the user can reopen a previous result without regenerating it.
  useEffect(() => {
    if (step !== 'input' || savedPlan) return
    const tripId = getCookie('g3ta_trip_id')
    if (!tripId) return
    loadLatestResult()
      .then((data) => setSavedPlan(data))
      .catch(() => {})
  }, [step, savedPlan])

  async function persistResult(planResult, input) {
    try {
      const data = await saveResult(planResult, input)
      if (data?.trip_id) {
        setCookie('g3ta_trip_id', data.trip_id)
        setSavedPlan({
          trip_id: data.trip_id,
          saved_at: new Date().toISOString(),
          input,
          result: planResult,
        })
      }
    } catch (err) {
      // Persisting is best-effort; never block the result view.
      console.warn('Could not persist result:', err)
    }
  }

  function viewSavedPlan() {
    if (!savedPlan?.result) return
    setResult(savedPlan.result)
    setTripInput(savedPlan.input || null)
    setTab('itinerary')
    setStep('result')
  }

  function newRequestId() {
    return globalThis.crypto?.randomUUID?.()
      || `${Date.now()}-${Math.random().toString(36).slice(2)}`
  }

  async function handleSubmit(input) {
    const previousRequestId = activeRequestIdRef.current
    planControllerRef.current?.abort()
    if (previousRequestId) {
      await cancelPlan(previousRequestId).catch(() => {})
    }
    const controller = new AbortController()
    planControllerRef.current = controller
    const preparedInput = { ...input, request_id: newRequestId() }
    activeRequestIdRef.current = preparedInput.request_id
    setError(null)
    setResult(null)
    setTripInput(preparedInput)
    setStatuses(Object.fromEntries(AGENTS.map((agent) => [agent, 'pending'])))
    setProgressEvents([])
    setStep('progress')
    window.scrollTo({ top: 0, behavior: 'smooth' })

    try {
      await streamPlan(preparedInput, (event) => {
        if (event.type === 'agent_start') {
          setStatuses((current) => ({ ...current, [event.agent]: 'running' }))
          setProgressEvents((current) => [...current, { ...event, type: 'start' }].slice(-40))
        } else if (event.type === 'agent_progress') {
          setProgressEvents((current) => [...current, { ...event, type: 'progress' }].slice(-40))
        } else if (event.type === 'agent_done') {
          setStatuses((current) => ({ ...current, [event.agent]: 'done' }))
          setProgressEvents((current) => [...current, { ...event, type: 'done' }].slice(-40))
        } else if (event.type === 'complete') {
          planControllerRef.current = null
          activeRequestIdRef.current = null
          setResult(event.result)
          setTab('itinerary')
          setStep('result')
          void persistResult(event.result, preparedInput)
        } else if (event.type === 'error') {
          planControllerRef.current = null
          activeRequestIdRef.current = null
          setError(event.message)
        } else if (event.type === 'cancelled') {
          planControllerRef.current = null
          activeRequestIdRef.current = null
          setError('Trip planning was cancelled.')
        }
      }, { signal: controller.signal })
    } catch (requestError) {
      if (activeRequestIdRef.current === preparedInput.request_id) {
        activeRequestIdRef.current = null
      }
      if (requestError.name !== 'AbortError') setError(requestError.message)
    }
  }

  const handleBudgetChange = useCallback(async (adjustedBudget) => {
    if (!tripInput || !result || !adjustedBudget) return
    setError(null)

    try {
      const data = await finalizePlan(tripInput, result, adjustedBudget)
      setResult(data)
    } catch (e) {
      setError(e.message)
    }
  }, [tripInput, result])

  const reset = useCallback(() => {
    planControllerRef.current?.abort()
    planControllerRef.current = null
    activeRequestIdRef.current = null
    setStep('input')
    setResult(null)
    setProgressEvents([])
    setError(null)
    setTab('itinerary')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }, [])

  async function cancelAndReset() {
    const requestId = activeRequestIdRef.current || tripInput?.request_id
    if (requestId && step === 'progress') {
      await cancelPlan(requestId).catch(() => {})
    }
    reset()
  }

  function requestReset() {
    if (settings.preset === 'senior' && step !== 'input') {
      setLeaveDialogOpen(true)
      return
    }
    cancelAndReset()
  }

  return (
    <div className={`app-shell view-${step}`}>
      <AppHeader
        step={step}
        onReset={requestReset}
        onAccessibility={() => setAccessibilityOpen(true)}
        accessibilityButtonRef={accessibilityButtonRef}
      />
      <AccessibilityPanel
        open={accessibilityOpen}
        onClose={() => setAccessibilityOpen(false)}
        returnFocusRef={accessibilityButtonRef}
      />
      <ConfirmationDialog
        open={leaveDialogOpen}
        title="Leave this trip?"
        description="Your current plan will close. Provider purchases are never changed by leaving G3TA."
        onCancel={() => setLeaveDialogOpen(false)}
        onConfirm={() => {
          setLeaveDialogOpen(false)
          cancelAndReset()
        }}
      />

      {step === 'input' && <Landing onSubmit={handleSubmit} savedPlan={savedPlan} onViewSaved={viewSavedPlan} />}

      {step === 'progress' && (
        <main className="progress-page">
          <ProgressTracker
            agents={AGENTS}
            statuses={statuses}
            events={progressEvents}
            trip={tripInput}
            error={error}
            onRetry={reset}
            onCancel={cancelAndReset}
          />
        </main>
      )}

      {step === 'result' && result && (
        <main className="result-page">
          <ResultHeader result={result} />
          {settings.preset === 'senior' && (
            <div className="senior-result-actions">
              <EmergencyInformation result={result} />
            </div>
          )}

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
                onBudgetChange={handleBudgetChange}
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
          </section>
        </main>
      )}

      {step === 'result' && result && settings.preset === 'senior' && (
        <NextStepHelper result={result} />
      )}

      <footer className="site-footer">
        <Brand />
        <p>Thoughtful journeys, composed by people and machines.</p>
        <span>DeepSeek-powered · G3TA 2026</span>
      </footer>
    </div>
  )
}
