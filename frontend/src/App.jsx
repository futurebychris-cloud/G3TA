import { useCallback, useEffect, useRef, useState } from 'react'
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
import BookingPanel from './components/BookingPanel.jsx'
import OrbitGlobe from './components/OrbitGlobe.jsx'
import AccessibilityButton from './components/accessibility/AccessibilityButton.jsx'
import AccessibilityPanel from './components/accessibility/AccessibilityPanel.jsx'
import AccessibilityOnboarding from './components/accessibility/AccessibilityOnboarding.jsx'
import ConfirmationDialog from './components/accessibility/ConfirmationDialog.jsx'
import EmergencyInformation from './components/accessibility/EmergencyInformation.jsx'
import LineFocusReader from './components/accessibility/LineFocusReader.jsx'
import NextStepHelper from './components/accessibility/NextStepHelper.jsx'
import ReadAloudButton from './components/accessibility/ReadAloudButton.jsx'
import GuidedTripAssistant from './components/accessibility/GuidedTripAssistant.jsx'
import { useAccessibilitySettings } from './accessibility/AccessibilityContext.jsx'
import { formatAccessibleDate, formatAccessibleMoney } from './utils/accessibility.js'

const AGENTS = ['budget', 'transportation', 'housing', 'food', 'activity', 'planning', 'orchestrator']

const TABS = [
  { id: 'itinerary', label: 'Itinerary', icon: Route },
  { id: 'map', label: 'Places', icon: Map },
  { id: 'budget', label: 'Budget', icon: CircleDollarSign },
  { id: 'stay', label: 'Book stay', icon: BedDouble },
  { id: 'packing', label: 'Packing', icon: Luggage },
  { id: 'reasoning', label: 'Agent log', icon: ListChecks },
]

function tripInputFromGuidedDraft(draft) {
  const travelers = Number(draft.num_people) || 1
  return {
    location: String(draft.location || '').trim(),
    origin: String(draft.origin || '').trim(),
    dates: {
      start: String(draft.dates?.start || ''),
      end: String(draft.dates?.end || ''),
    },
    budget: {
      total: Number(draft.budget?.total),
      currency: String(draft.budget?.currency || 'USD').trim().toUpperCase(),
    },
    preferences: {
      bites: draft.preferences?.bites || [],
      transportation_type: draft.preferences?.transportation_type || [],
      activity_style: draft.preferences?.activity_style || [],
    },
    time_constraints: String(draft.time_constraints || '').trim(),
    must_go_sites: draft.must_go_sites || [],
    num_people: travelers,
    is_group: travelers >= 5,
  }
}

function Brand() {
  return (
    <div className="brand" aria-label="vibego home">
      <span className="brand-mark"><Compass size={19} strokeWidth={2.2} /></span>
      <span className="brand-word">vibego</span>
      <span className="brand-divider" />
      <span className="brand-sub">Journey intelligence</span>
    </div>
  )
}

function AppHeader({ step, onReset, onAccessibility, accessibilityButtonRef }) {
  return (
    <header className="site-header">
      <button className="brand-button" type="button" onClick={onReset} aria-label="vibego trip planner home">
        <Brand />
      </button>
      <div className="header-actions">
        <span className="system-status"><span className="status-light" /> Planning workspace ready</span>
        {step !== 'input' && (
          <button className="text-button" onClick={onReset}>
            <ArrowLeft size={16} /> New journey
          </button>
        )}
        <AccessibilityButton onClick={onAccessibility} buttonRef={accessibilityButtonRef} />
      </div>
    </header>
  )
}

function Landing({ onSubmit, intakeDraft, intakeNotice }) {
  return (
    <main className="landing" id="main-content" tabIndex="-1">
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
        <InputForm onSubmit={onSubmit} intakeDraft={intakeDraft} intakeNotice={intakeNotice} />
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
  const { settings } = useAccessibilitySettings()
  const start = new Date(`${result.dates.start}T00:00:00`)
  const end = new Date(`${result.dates.end}T00:00:00`)
  const duration = Math.max(1, Math.round((end - start) / 86400000) + 1)
  const dateLabel = settings.easyReading
    ? `${formatAccessibleDate(result.dates.start)} to ${formatAccessibleDate(result.dates.end)}`
    : `${start.toLocaleDateString('en', { month: 'short', day: 'numeric' })} — ${end.toLocaleDateString('en', { month: 'short', day: 'numeric', year: 'numeric' })}`
  const totalLabel = formatAccessibleMoney(result.cost.currency, result.cost.total)
  const spokenSummary = [
    `Trip to ${result.destination}`,
    `Dates: ${dateLabel}`,
    `Duration: ${duration} days`,
    `Estimated total: ${totalLabel}`,
    result.cost.within_budget ? 'Status: within budget' : 'Status: needs review',
    result.summary,
    result.verification_notice,
  ]

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
      <div className="result-heading-actions">
        <ReadAloudButton id="trip-summary" text={spokenSummary} label={`trip summary for ${result.destination}`} />
      </div>
      <LineFocusReader text={result.summary} className="trip-summary" />
      <div className="trip-facts">
        <div><CalendarDays size={18} /><span><small>DATES</small>{dateLabel}</span></div>
        <div><Route size={18} /><span><small>DURATION</small>{duration} days</span></div>
        <div><CircleDollarSign size={18} aria-hidden="true" /><span><small>ESTIMATED</small>{totalLabel}</span></div>
        <div><Check size={18} /><span><small>STATUS</small>{result.cost.within_budget ? 'Within budget' : 'Needs review'}</span></div>
      </div>
      {result.verification_notice && (
        <div className="verification-banner" role="note" aria-label="Planning estimate warning">
          <ShieldAlert size={18} aria-hidden="true" />
          <span><strong>Planning estimate</strong>{result.verification_notice}</span>
        </div>
      )}
    </section>
  )
}

export default function App() {
  const { settings } = useAccessibilitySettings()
  const [step, setStep] = useState('input')
  const [statuses, setStatuses] = useState({})
  const [agentEvents, setAgentEvents] = useState([])
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [tab, setTab] = useState('itinerary')
  const [tripInput, setTripInput] = useState(null)
  const [accessibilityOpen, setAccessibilityOpen] = useState(false)
  const [guidedTripOpen, setGuidedTripOpen] = useState(false)
  const [intakeDraft, setIntakeDraft] = useState(null)
  const [intakeNotice, setIntakeNotice] = useState(null)
  const [resetConfirmationOpen, setResetConfirmationOpen] = useState(false)
  const [showAllTabs, setShowAllTabs] = useState(false)
  const accessibilityButtonRef = useRef(null)
  const requestControllerRef = useRef(null)
  const resultTransitionTimerRef = useRef(null)
  const requestVersionRef = useRef(0)
  const isSenior = settings.preset === 'senior'
  const visibleTabs = isSenior && !showAllTabs
    ? TABS.filter(({ id }) => ['itinerary', 'map', 'packing'].includes(id))
    : TABS

  const closeAccessibility = useCallback(() => setAccessibilityOpen(false), [])

  function openGuidedTrip() {
    setAccessibilityOpen(false)
    window.setTimeout(() => setGuidedTripOpen(true), 0)
  }

  function completeGuidedTrip(draft, notice) {
    setIntakeDraft({ ...draft, appliedAt: Date.now() })
    setIntakeNotice(notice)
    setGuidedTripOpen(false)
    void handleSubmit(tripInputFromGuidedDraft(draft))
  }

  useEffect(() => {
    if (!isSenior && showAllTabs) setShowAllTabs(false)
    if (isSenior && !showAllTabs && !['itinerary', 'map', 'packing'].includes(tab)) {
      setTab('itinerary')
    }
  }, [isSenior, showAllTabs, tab])

  useEffect(() => () => {
    requestVersionRef.current += 1
    requestControllerRef.current?.abort()
    if (resultTransitionTimerRef.current) window.clearTimeout(resultTransitionTimerRef.current)
  }, [])

  async function handleSubmit(input) {
    const requestId = ++requestVersionRef.current
    if (resultTransitionTimerRef.current) {
      window.clearTimeout(resultTransitionTimerRef.current)
      resultTransitionTimerRef.current = null
    }
    setError(null)
    setResult(null)
    setAgentEvents([])
    setTripInput(input)
    setStatuses(Object.fromEntries(AGENTS.map((agent) => [agent, 'pending'])))
    setStep('progress')
    setShowAllTabs(false)
    window.scrollTo({ top: 0, behavior: settings.reducedMotion ? 'auto' : 'smooth' })

    requestControllerRef.current?.abort()
    const controller = new AbortController()
    requestControllerRef.current = controller
    try {
      await streamPlan({
        ...input,
        accessibility: {
          easy_reading: settings.easyReading,
          preset: settings.preset,
        },
      }, (event) => {
        if (requestId !== requestVersionRef.current || controller.signal.aborted) return
        if (event.type === 'agent_start') {
          setStatuses((current) => ({ ...current, [event.agent]: 'running' }))
          setAgentEvents((current) => [...current, { agent: event.agent, type: 'start' }])
        } else if (event.type === 'agent_done') {
          setStatuses((current) => ({ ...current, [event.agent]: 'done' }))
          setAgentEvents((current) => [...current, { agent: event.agent, type: 'done', output: event.output || null }])
        } else if (event.type === 'complete') {
          setResult(event.result)
          resultTransitionTimerRef.current = window.setTimeout(() => {
            if (requestId !== requestVersionRef.current) return
            setTab('itinerary')
            setStep('result')
            resultTransitionTimerRef.current = null
          }, settings.reducedMotion ? 0 : 800)
        } else if (event.type === 'error') {
          setError(event.message)
        }
      }, { signal: controller.signal })
    } catch (requestError) {
      if (requestId === requestVersionRef.current && requestError.name !== 'AbortError') setError(requestError.message)
    } finally {
      if (requestControllerRef.current === controller) requestControllerRef.current = null
    }
  }

  function completeReset() {
    requestVersionRef.current += 1
    requestControllerRef.current?.abort()
    requestControllerRef.current = null
    if (resultTransitionTimerRef.current) {
      window.clearTimeout(resultTransitionTimerRef.current)
      resultTransitionTimerRef.current = null
    }
    setStep('input')
    setStatuses({})
    setAgentEvents([])
    setResult(null)
    setError(null)
    setTab('itinerary')
    setTripInput(null)
    setIntakeDraft(null)
    setIntakeNotice(null)
    setShowAllTabs(false)
    setResetConfirmationOpen(false)
    window.scrollTo({ top: 0, behavior: settings.reducedMotion ? 'auto' : 'smooth' })
  }

  function requestReset() {
    if (isSenior && step !== 'input') {
      setResetConfirmationOpen(true)
      return
    }
    completeReset()
  }

  function selectTab(event, id, index, tabs) {
    if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
      event.preventDefault()
      const direction = event.key === 'ArrowRight' ? 1 : -1
      const nextIndex = (index + direction + tabs.length) % tabs.length
      setTab(tabs[nextIndex].id)
      document.getElementById(`trip-tab-${tabs[nextIndex].id}`)?.focus()
    } else if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault()
      const nextIndex = event.key === 'Home' ? 0 : tabs.length - 1
      setTab(tabs[nextIndex].id)
      document.getElementById(`trip-tab-${tabs[nextIndex].id}`)?.focus()
    } else if (event.key === 'Enter' || event.key === ' ') {
      setTab(id)
    }
  }

  return (
    <div className={`app-shell view-${step}`}>
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <AppHeader
        step={step}
        onReset={requestReset}
        onAccessibility={() => setAccessibilityOpen(true)}
        accessibilityButtonRef={accessibilityButtonRef}
      />
      <AccessibilityPanel
        open={accessibilityOpen}
        onClose={closeAccessibility}
        returnFocusRef={accessibilityButtonRef}
        onOpenTripAssistant={openGuidedTrip}
      />
      <GuidedTripAssistant
        open={guidedTripOpen}
        onClose={() => setGuidedTripOpen(false)}
        onComplete={completeGuidedTrip}
        returnFocusRef={accessibilityButtonRef}
      />
      <AccessibilityOnboarding />
      <ConfirmationDialog
        open={resetConfirmationOpen}
        title="Start a new journey?"
        description="Your current trip will leave this screen. You can cancel and keep reading it."
        onCancel={() => setResetConfirmationOpen(false)}
        onConfirm={completeReset}
      />

      {step === 'input' && (
        <Landing
          onSubmit={handleSubmit}
          intakeDraft={intakeDraft}
          intakeNotice={intakeNotice}
        />
      )}

      {step === 'progress' && (
        <main className="progress-page" id="main-content" tabIndex="-1">
          <ProgressTracker agents={AGENTS} statuses={statuses} events={agentEvents} trip={tripInput} error={error} onRetry={requestReset} />
        </main>
      )}

      {step === 'result' && result && (
        <main className="result-page" id="main-content" tabIndex="-1">
          <ResultHeader result={result} />

          {isSenior && (
            <div className="senior-result-actions" aria-label="Important trip tools">
              <EmergencyInformation result={result} />
            </div>
          )}

          <div className="result-tabs" role="tablist" aria-label="Trip details">
            {visibleTabs.map(({ id, label, icon: Icon }, index) => (
              <button
                id={`trip-tab-${id}`}
                key={id}
                type="button"
                role="tab"
                aria-selected={tab === id}
                aria-controls="trip-tab-panel"
                tabIndex={tab === id ? 0 : -1}
                className={tab === id ? 'result-tab active' : 'result-tab'}
                onClick={() => setTab(id)}
                onKeyDown={(event) => selectTab(event, id, index, visibleTabs)}
              >
                <Icon size={17} strokeWidth={1.8} />
                {label}
              </button>
            ))}
          </div>
          {isSenior && (
            <button
              className="show-more-sections"
              type="button"
              aria-expanded={showAllTabs}
              onClick={() => setShowAllTabs((current) => !current)}
            >
              {showAllTabs ? 'Show fewer trip sections' : 'Show all trip sections'}
            </button>
          )}

          <section
            id="trip-tab-panel"
            className="result-panel"
            role="tabpanel"
            aria-labelledby={`trip-tab-${tab}`}
            tabIndex="0"
          >
            {tab === 'itinerary' && <ItineraryView result={result} />}
            {tab === 'map' && <MapView points={result.map_points} result={result} />}
            {tab === 'stay' && tripInput && <BookingPanel trip={tripInput} />}
            {tab === 'budget' && <BudgetView cost={result.cost} budgetAgent={result.agent_outputs.budget} />}
            {tab === 'packing' && (
              <PackingList
                items={result.packing_list}
                weather={result.weather_summary}
                pacing={result.agent_outputs.planning.pacing_notes}
                dailyWeather={result.agent_outputs.planning.daily_weather}
                healthAdvice={result.agent_outputs.planning.health_advice}
              />
            )}
            {tab === 'reasoning' && <ReasoningLog log={result.reasoning_log} />}
          </section>
          {['open_meteo_forecast', 'mixed'].includes(result.weather_source) && (
            <p className="weather-attribution">
              Weather data by <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">Open-Meteo.com</a>
              {' · '}<a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">CC BY 4.0</a>
              {' · '}normalized for this itinerary by vibego
            </p>
          )}
          {isSenior && <NextStepHelper result={result} />}
        </main>
      )}

      <footer className="site-footer">
        <Brand />
        <p>Thoughtful journeys, composed by people and machines.</p>
        <span>DeepSeek-powered · vibego 2026</span>
      </footer>
    </div>
  )
}
