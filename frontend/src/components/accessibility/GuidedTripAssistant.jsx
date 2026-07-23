import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, Check, RotateCcw, ShieldCheck, Volume2, X } from 'lucide-react'
import { parseTripIntake } from '../../api.js'
import useTextToSpeech from '../../hooks/useTextToSpeech.js'
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
    prompt: 'Going to. What city and country would you like to visit?',
    hint: 'Say the city first, then the country. For example, Milan, Italy.',
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

function answersForAssistant(answers) {
  return QUESTIONS.map((question) => (
    `${question.label}: ${answers[question.id]?.trim() || 'None'}`
  )).join('\n')
}

export default function GuidedTripAssistant({ open, onClose, onComplete, returnFocusRef }) {
  const closeRef = useRef(null)
  const answerRef = useRef(null)
  const intakeRequestVersionRef = useRef(0)
  const openRef = useRef(open)
  openRef.current = open
  const [step, setStep] = useState(0)
  const [answers, setAnswers] = useState({})
  const [status, setStatus] = useState('answering')
  const [error, setError] = useState('')
  const [repairMessage, setRepairMessage] = useState('')
  const [repairQuestionIds, setRepairQuestionIds] = useState([])
  const question = QUESTIONS[step]
  const guidedSpeech = useTextToSpeech('guided-trip-assistant', '')

  const closeGuided = useCallback(() => {
    intakeRequestVersionRef.current += 1
    guidedSpeech.stop()
    onClose()
  }, [guidedSpeech.stop, onClose])

  const speakQuestion = useCallback((prefix = '') => {
    guidedSpeech.playText(`${prefix}${question.prompt}`, { force: true })
  }, [guidedSpeech.playText, question.prompt])

  useEffect(() => {
    if (!open || status === 'loading') return undefined
    const timer = window.setTimeout(() => speakQuestion(repairMessage ? `${repairMessage} ` : ''), 260)
    return () => window.clearTimeout(timer)
  }, [open, repairMessage, speakQuestion, status, step])

  useEffect(() => {
    if (!open) {
      intakeRequestVersionRef.current += 1
      guidedSpeech.stop()
    }
  }, [guidedSpeech.stop, open])

  useEffect(() => () => {
    intakeRequestVersionRef.current += 1
  }, [])

  function move(direction, answerSet = answers) {
    const answer = answerSet[question.id]?.trim() || ''
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
        reviewAnswers(answerSet)
      }
      return
    }
    setStep((current) => Math.max(0, Math.min(QUESTIONS.length - 1, current + direction)))
  }

  async function reviewAnswers(answerSet = answers) {
    const answer = answerSet[question.id]?.trim() || ''
    if (question.required && (!answer || answer.toLowerCase() === 'none')) {
      setError(`Please answer ${question.label.toLowerCase()} before continuing.`)
      answerRef.current?.focus()
      speakQuestion('I still need this answer. ')
      return
    }
    setStatus('loading')
    setError('')
    guidedSpeech.stop()
    const requestVersion = ++intakeRequestVersionRef.current
    try {
      const parsed = await parseTripIntake(answersForAssistant(answerSet))
      if (requestVersion !== intakeRequestVersionRef.current || !openRef.current) return
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
      setRepairQuestionIds([])
      setStatus('starting')
      guidedSpeech.stop()
      onComplete(parsed.draft, {
        summary: parsed.summary,
        missing: [],
        uncertain: parsed.uncertain,
      })
      closeGuided()
    } catch (requestError) {
      if (requestVersion !== intakeRequestVersionRef.current || !openRef.current) return
      setError(`${requestError.message} Your answers have not been lost. Choose Start planning again to retry.`)
      setStatus('answering')
    }
  }

  function startOver() {
    intakeRequestVersionRef.current += 1
    setAnswers({})
    setStep(0)
    setStatus('answering')
    setError('')
    setRepairMessage('')
    setRepairQuestionIds([])
  }

  function acceptVoiceAnswer(transcript, { isFinal = true } = {}) {
    const nextAnswers = { ...answers, [question.id]: transcript }
    setAnswers(nextAnswers)
    setError('')
    if (!isFinal) return
    if (isLastQuestion) {
      reviewAnswers(nextAnswers)
    } else {
      move(1, nextAnswers)
    }
  }

  const currentAnswer = answers[question.id] || ''
  const speechSupported = guidedSpeech.supported
  const repairIndex = repairQuestionIds.indexOf(question.id)
  const canGoBack = repairQuestionIds.length > 0 ? repairIndex > 0 : step > 0
  const isLastQuestion = repairQuestionIds.length > 0
    ? repairIndex === repairQuestionIds.length - 1
    : step === QUESTIONS.length - 1

  return (
    <AccessibleDialog
      open={open}
      onClose={closeGuided}
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
            The guide asks the same questions as the main form, one at a time. A final voice answer starts trip planning automatically.
          </p>
        </div>
        <button ref={closeRef} className="dialog-close" type="button" onClick={closeGuided} aria-label="Close voice-guided trip setup">
          <X size={20} aria-hidden="true" />
        </button>
      </header>

      <div className="guided-trip-body">
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
              <>
                <button
                  className="replay-question"
                  type="button"
                  onClick={() => speakQuestion()}
                  disabled={guidedSpeech.state === 'loading'}
                >
                  <Volume2 size={17} aria-hidden="true" />
                  {guidedSpeech.state === 'loading' ? 'Preparing voice…' : 'Replay question'}
                </button>
                <span className="sr-only" role="status" aria-live="polite">
                  {guidedSpeech.state === 'loading'
                    ? 'Preparing the Piper voice'
                    : guidedSpeech.state === 'speaking'
                      ? 'Piper is reading the question'
                      : guidedSpeech.error}
                </span>
              </>
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
              onTranscript={acceptVoiceAnswer}
            />
          </div>
          <p id="guided-answer-hint" className="guided-privacy">
            <ShieldCheck size={16} aria-hidden="true" />
            Voice answers advance automatically. After the final answer, planning starts. Missing required details stay in this guide.
          </p>
          <p id="guided-trip-error" className="guided-error" role="alert">{error}</p>
        </>
      </div>

      <footer className="accessibility-panel-actions guided-trip-actions">
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
            <button className="done-accessibility" type="button" onClick={() => reviewAnswers()} disabled={status === 'loading'}>
              {status === 'loading' ? 'Starting your trip…' : 'Start planning'} <Check size={16} aria-hidden="true" />
            </button>
          )}
        </div>
      </footer>
    </AccessibleDialog>
  )
}
