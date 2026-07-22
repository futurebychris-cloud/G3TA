import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, Check, RotateCcw, ShieldCheck, Volume2, X } from 'lucide-react'
import { parseTripIntake } from '../../api.js'
import { useAccessibilitySettings } from '../../accessibility/AccessibilityContext.jsx'
import AccessibleDialog from './AccessibleDialog.jsx'
import VoiceInputButton from './VoiceInputButton.jsx'

const QUESTIONS = [
  {
    id: 'origin',
    label: 'Flying from',
    prompt: 'Flying from. What city are you leaving from?',
    hint: 'For example, New York or Shanghai.',
    required: true,
  },
  {
    id: 'location',
    label: 'Going to',
    prompt: 'Going to. What city or country would you like to visit?',
    hint: 'For example, Tokyo or Portugal.',
    required: true,
  },
  {
    id: 'start_date',
    label: 'Start date',
    prompt: 'Start date. When would you like your trip to begin?',
    hint: 'You can say a date naturally, such as October tenth, twenty twenty-six.',
    required: true,
  },
  {
    id: 'end_date',
    label: 'End date',
    prompt: 'End date. When would you like your trip to end?',
    hint: 'You can say a date, or describe how many days you want to travel.',
    required: true,
  },
  {
    id: 'budget',
    label: 'Total budget',
    prompt: 'Total budget. What is your total budget, including the currency?',
    hint: 'For example, four thousand US dollars or twenty thousand yuan.',
    required: true,
  },
  {
    id: 'cuisines',
    label: 'Cuisine preferences',
    prompt: 'Cuisine preferences. Which cuisines do you prefer? You can name more than one.',
    hint: 'For example, Japanese and Italian. You can also say no preference.',
  },
  {
    id: 'activity_styles',
    label: 'Travel energy',
    prompt: 'Travel energy. Would you like cultural, adventure, relaxed, or a mix?',
    hint: 'Say one choice or combine them.',
  },
  {
    id: 'transportation',
    label: 'Preferred transport',
    prompt: 'Preferred transport. Would you prefer flight, train, or car?',
    hint: 'You can name more than one.',
  },
  {
    id: 'time_constraints',
    label: 'Anything we should work around?',
    prompt: 'Anything we should work around? Tell us about timing or accessibility needs.',
    hint: 'You can say none if there is nothing to add.',
  },
  {
    id: 'must_go_sites',
    label: 'Must-see places',
    prompt: 'Must-see places. Are there any places you definitely want to visit?',
    hint: 'Name one or more places, or say none.',
  },
  {
    id: 'num_people',
    label: 'Travelers',
    prompt: 'Travelers. How many people are going?',
    hint: 'Include yourself in the total.',
    required: true,
  },
]

const FIELD_TO_QUESTION = {
  origin: 'origin',
  location: 'location',
  start_date: 'start_date',
  end_date: 'end_date',
  budget_total: 'budget',
  currency: 'budget',
  num_people: 'num_people',
  cuisines: 'cuisines',
  transportation: 'transportation',
  activity_styles: 'activity_styles',
  time_constraints: 'time_constraints',
  must_go_sites: 'must_go_sites',
}

const FIELD_LABELS = Object.fromEntries(QUESTIONS.map(({ id, label }) => [id, label]))
FIELD_LABELS.budget_total = 'Total budget'
FIELD_LABELS.currency = 'Budget currency'

function display(value, fallback = 'No preference') {
  if (Array.isArray(value)) return value.length ? value.join(', ') : fallback
  if (value === null || value === undefined || value === '') return fallback
  return String(value)
}

function DraftReview({ result }) {
  const { draft } = result
  const fields = [
    ['From', display(draft.origin, 'Not provided')],
    ['Going to', display(draft.location, 'Not provided')],
    ['Dates', `${display(draft.dates.start, 'Not provided')} to ${display(draft.dates.end, 'Not provided')}`],
    ['Budget', draft.budget.total
      ? `${display(draft.budget.currency, '')} ${draft.budget.total}`.trim()
      : 'Not provided'],
    ['Travelers', display(draft.num_people, 'Not provided')],
    ['Food', display(draft.preferences.bites)],
    ['Transport', display(draft.preferences.transportation_type)],
    ['Trip style', display(draft.preferences.activity_style)],
    ['Timing and access needs', display(draft.time_constraints)],
    ['Must-see places', display(draft.must_go_sites)],
  ]

  return (
    <div className="guided-review">
      <div className="guided-review-summary" role="status">
        <Check size={19} aria-hidden="true" />
        <div><strong>Your answers are ready</strong><p>{result.summary}</p></div>
      </div>
      <dl className="guided-review-grid">
        {fields.map(([label, value]) => (
          <div key={label}><dt>{label}</dt><dd>{value}</dd></div>
        ))}
      </dl>
      {result.uncertain.length > 0 && (
        <div className="guided-review-note" role="note">
          <strong>Please double-check:</strong>{' '}
          {result.uncertain.map((field) => FIELD_LABELS[FIELD_TO_QUESTION[field]] || field).join(', ')}.
        </div>
      )}
    </div>
  )
}

function answersForAssistant(answers) {
  return QUESTIONS.map((question) => (
    `${question.label}: ${answers[question.id]?.trim() || 'None'}`
  )).join('\n')
}

export default function GuidedTripAssistant({ open, onClose, onApplyDraft, returnFocusRef }) {
  const { settings } = useAccessibilitySettings()
  const closeRef = useRef(null)
  const answerRef = useRef(null)
  const [step, setStep] = useState(0)
  const [answers, setAnswers] = useState({})
  const [result, setResult] = useState(null)
  const [status, setStatus] = useState('answering')
  const [error, setError] = useState('')
  const [repairMessage, setRepairMessage] = useState('')
  const [repairQuestionIds, setRepairQuestionIds] = useState([])
  const question = QUESTIONS[step]

  const speakQuestion = useCallback((prefix = '') => {
    if (typeof window === 'undefined'
      || !('speechSynthesis' in window)
      || typeof window.SpeechSynthesisUtterance !== 'function') return
    window.speechSynthesis.cancel()
    const utterance = new window.SpeechSynthesisUtterance(`${prefix}${question.prompt}`)
    utterance.rate = settings.readingSpeed
    window.speechSynthesis.speak(utterance)
  }, [question.prompt, settings.readingSpeed])

  useEffect(() => {
    if (!open || result || status === 'loading') return undefined
    const timer = window.setTimeout(() => speakQuestion(repairMessage ? `${repairMessage} ` : ''), 260)
    return () => window.clearTimeout(timer)
  }, [open, repairMessage, result, speakQuestion, status, step])

  useEffect(() => () => window.speechSynthesis?.cancel(), [])

  function move(direction) {
    const answer = answers[question.id]?.trim() || ''
    if (direction > 0 && question.required && (!answer || answer.toLowerCase() === 'none')) {
      setError(`Please answer ${question.label.toLowerCase()} before continuing. You can speak or type your answer.`)
      answerRef.current?.focus()
      speakQuestion('I still need this answer. ')
      return
    }
    setError('')
    setRepairMessage('')
    if (repairQuestionIds.length > 0) {
      const repairIndex = repairQuestionIds.indexOf(question.id)
      const nextRepair = repairQuestionIds[repairIndex + direction]
      if (nextRepair) {
        setStep(QUESTIONS.findIndex(({ id }) => id === nextRepair))
      } else if (direction > 0) {
        reviewAnswers()
      }
      return
    }
    setStep((current) => Math.max(0, Math.min(QUESTIONS.length - 1, current + direction)))
  }

  async function reviewAnswers() {
    const answer = answers[question.id]?.trim() || ''
    if (question.required && (!answer || answer.toLowerCase() === 'none')) {
      setError(`Please answer ${question.label.toLowerCase()} before continuing.`)
      answerRef.current?.focus()
      speakQuestion('I still need this answer. ')
      return
    }
    setStatus('loading')
    setError('')
    window.speechSynthesis?.cancel()
    try {
      const parsed = await parseTripIntake(answersForAssistant(answers))
      if (parsed.missing.length > 0) {
        const missingQuestionIds = [...new Set(parsed.missing.map((field) => FIELD_TO_QUESTION[field]).filter(Boolean))]
        const nextIndex = QUESTIONS.findIndex(({ id }) => missingQuestionIds.includes(id))
        const missingLabels = [...new Set(parsed.missing.map((field) => FIELD_LABELS[field] || field))]
        setRepairMessage(`I could not confirm ${missingLabels.join(' and ')}.`)
        setRepairQuestionIds(missingQuestionIds)
        setStep(nextIndex >= 0 ? nextIndex : 0)
        setStatus('answering')
        setError('Please answer this question again. You will stay in guided setup until the required details are complete.')
        window.setTimeout(() => answerRef.current?.focus(), 0)
        return
      }
      setResult(parsed)
      setRepairQuestionIds([])
      setStatus('review')
      if (speechSupported) {
        const reviewSpeech = new window.SpeechSynthesisUtterance(
          `Your trip details are ready to review. ${parsed.summary}`,
        )
        reviewSpeech.rate = settings.readingSpeed
        window.speechSynthesis.speak(reviewSpeech)
      }
    } catch (requestError) {
      setError(`${requestError.message} Your answers have not been lost. Choose review again to retry.`)
      setStatus('answering')
    }
  }

  function editAnswers() {
    setResult(null)
    setStep(0)
    setStatus('answering')
    setError('')
    setRepairMessage('')
    setRepairQuestionIds([])
    window.setTimeout(() => answerRef.current?.focus(), 0)
  }

  function startOver() {
    setAnswers({})
    setResult(null)
    setStep(0)
    setStatus('answering')
    setError('')
    setRepairMessage('')
    setRepairQuestionIds([])
  }

  function applyDraft() {
    onApplyDraft(result.draft, {
      summary: result.summary,
      missing: [],
      uncertain: result.uncertain,
    })
    onClose()
  }

  const currentAnswer = answers[question.id] || ''
  const speechSupported = typeof window !== 'undefined'
    && 'speechSynthesis' in window
    && typeof window.SpeechSynthesisUtterance === 'function'
  const repairIndex = repairQuestionIds.indexOf(question.id)
  const canGoBack = repairQuestionIds.length > 0 ? repairIndex > 0 : step > 0
  const isLastQuestion = repairQuestionIds.length > 0
    ? repairIndex === repairQuestionIds.length - 1
    : step === QUESTIONS.length - 1

  return (
    <AccessibleDialog
      open={open}
      onClose={onClose}
      returnFocusRef={returnFocusRef}
      initialFocusRef={closeRef}
      labelledBy="guided-trip-title"
      describedBy="guided-trip-description"
      className="accessibility-panel guided-trip-dialog"
    >
      <header className="accessibility-panel-head">
        <div>
          <span className="section-index">OPTIONAL DYSLEXIA &amp; READING SUPPORT</span>
          <h2 id="guided-trip-title">Voice-guided trip setup</h2>
          <p id="guided-trip-description">
            The guide asks the same questions as the main form, one at a time. Answer by voice or typing, then review the completed details.
          </p>
        </div>
        <button ref={closeRef} className="dialog-close" type="button" onClick={onClose} aria-label="Close voice-guided trip setup">
          <X size={20} aria-hidden="true" />
        </button>
      </header>

      <div className="guided-trip-body">
        {!result ? (
          <>
            <div className="guided-progress" aria-label={`Question ${step + 1} of ${QUESTIONS.length}`}>
              <div><strong>Question {step + 1} of {QUESTIONS.length}</strong><span>{Math.round(((step + 1) / QUESTIONS.length) * 100)}% complete</span></div>
              <progress max={QUESTIONS.length} value={step + 1}>{step + 1} of {QUESTIONS.length}</progress>
            </div>

            <section className="guided-question" aria-labelledby="guided-question-label">
              <span className="section-index">{question.label}</span>
              <h3 id="guided-question-label">{question.prompt}</h3>
              <p>{question.hint}</p>
              {speechSupported && (
                <button className="replay-question" type="button" onClick={() => speakQuestion()}>
                  <Volume2 size={17} aria-hidden="true" /> Replay question
                </button>
              )}
            </section>

            <label className="guided-description-field" htmlFor="guided-trip-answer">
              Your answer {question.required ? '' : '(optional)'}
            </label>
            <div className="guided-description-input guided-answer-input">
              <textarea
                ref={answerRef}
                id="guided-trip-answer"
                value={currentAnswer}
                onChange={(event) => setAnswers((current) => ({ ...current, [question.id]: event.target.value }))}
                rows="3"
                maxLength="500"
                aria-describedby="guided-answer-hint guided-trip-error"
                placeholder="Speak your answer or type it here"
              />
              <VoiceInputButton
                label={`Answer ${question.label.toLowerCase()} by voice`}
                showText
                onTranscript={(transcript) => {
                  setAnswers((current) => ({ ...current, [question.id]: transcript }))
                  setError('')
                }}
              />
            </div>
            <p id="guided-answer-hint" className="guided-privacy">
              <ShieldCheck size={16} aria-hidden="true" />
              Your spoken answer appears above so you can check it. The guide will ask again if a required detail is missing.
            </p>
            <p id="guided-trip-error" className="guided-error" role="alert">{error}</p>
          </>
        ) : <DraftReview result={result} />}
      </div>

      <footer className="accessibility-panel-actions guided-trip-actions">
        {result ? (
          <>
            <button className="reset-accessibility" type="button" onClick={editAnswers}>
              <ArrowLeft size={16} aria-hidden="true" /> Edit answers
            </button>
            <button className="done-accessibility" type="button" onClick={applyDraft}>
              Fill the trip form <Check size={16} aria-hidden="true" />
            </button>
          </>
        ) : (
          <>
            <button className="reset-accessibility start-over-button" type="button" onClick={startOver}>
              <RotateCcw size={16} aria-hidden="true" /> Start over
            </button>
            <div className="guided-step-actions">
              {canGoBack && (
                <button className="reset-accessibility" type="button" onClick={() => move(-1)}>
                  <ArrowLeft size={16} aria-hidden="true" /> Back
                </button>
              )}
              {!isLastQuestion ? (
                <button className="done-accessibility" type="button" onClick={() => move(1)}>
                  {currentAnswer.trim() || question.required ? 'Next question' : 'Skip question'} <ArrowRight size={16} aria-hidden="true" />
                </button>
              ) : (
                <button className="done-accessibility" type="button" onClick={reviewAnswers} disabled={status === 'loading'}>
                  {status === 'loading' ? 'Preparing your details…' : 'Review my answers'} <Check size={16} aria-hidden="true" />
                </button>
              )}
            </div>
          </>
        )}
      </footer>
    </AccessibleDialog>
  )
}
