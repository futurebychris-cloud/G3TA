import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, Check, RotateCcw, ShieldCheck, Volume2, X } from 'lucide-react'
import { parseTripIntake } from '../../api.js'
import useTextToSpeech from '../../hooks/useTextToSpeech.js'
import AccessibleDialog from './AccessibleDialog.jsx'
import VoiceInputButton from './VoiceInputButton.jsx'

const ENGLISH_QUESTIONS = [
  {
    id: 'origin',
    label: 'Flying from',
    prompt: 'Where will you be traveling from?',
    hint: 'Just tell us the city, like New York or Shanghai.',
    required: true,
  },
  {
    id: 'location',
    label: 'Going to',
    prompt: 'Where would you love to go?',
    hint: 'Tell us the city and country, like Milan, Italy.',
    required: true,
  },
  {
    id: 'start_date',
    label: 'Start date',
    prompt: 'When would you like your trip to begin?',
    hint: 'Say the date naturally, like October tenth, twenty twenty-six.',
    required: true,
  },
  {
    id: 'end_date',
    label: 'End date',
    prompt: 'And when would you like to come home?',
    hint: 'Say a date, or simply tell us how many days you would like to travel.',
    required: true,
  },
  {
    id: 'budget',
    label: 'Total budget',
    prompt: 'What budget would you like us to plan around?',
    hint: 'Include the currency—for example, four thousand US dollars or twenty thousand yuan.',
    required: true,
  },
  {
    id: 'cuisines',
    label: 'Cuisine preferences',
    prompt: 'What kinds of food would make this trip special for you?',
    hint: 'Name as many as you like, such as Japanese and Italian, or say you have no preference.',
  },
  {
    id: 'activity_styles',
    label: 'Travel energy',
    prompt: 'What kind of pace feels right for this trip?',
    hint: 'You can say cultural, adventurous, relaxed, or a mix.',
  },
  {
    id: 'transportation',
    label: 'Preferred transport',
    prompt: 'How would you prefer to get there?',
    hint: 'Choose a flight, train, car, or any combination that works for you.',
  },
  {
    id: 'time_constraints',
    label: 'Anything we should work around?',
    prompt: 'Is there anything about timing or accessibility we should plan around?',
    hint: 'If not, you can simply say “nothing.”',
  },
  {
    id: 'must_go_sites',
    label: 'Must-see places',
    prompt: 'Is there anywhere you would be disappointed to miss?',
    hint: 'Name one or more places, or say you do not have any must-sees.',
  },
  {
    id: 'num_people',
    label: 'Travelers',
    prompt: 'How many people are joining the trip?',
    hint: 'Remember to include yourself.',
    required: true,
  },
]

const CHINESE_QUESTIONS = [
  {
    id: 'origin',
    label: '出发城市',
    prompt: '您将从哪个城市出发？',
    hint: '例如：纽约或上海。',
    required: true,
  },
  {
    id: 'location',
    label: '旅行目的地',
    prompt: '您想去哪个城市和国家旅行？',
    hint: '请先说城市，再说国家。例如：意大利米兰。',
    required: true,
  },
  {
    id: 'start_date',
    label: '出发日期',
    prompt: '您希望什么时候开始旅行？',
    hint: '您可以自然地说出日期，例如：二〇二六年十月十日。',
    required: true,
  },
  {
    id: 'end_date',
    label: '结束日期',
    prompt: '您希望什么时候结束旅行？',
    hint: '您可以说出日期，也可以告诉我们计划旅行几天。',
    required: true,
  },
  {
    id: 'budget',
    label: '总预算',
    prompt: '您的旅行总预算是多少？请包括币种。',
    hint: '例如：四千美元或两万元人民币。',
    required: true,
  },
  {
    id: 'cuisines',
    label: '饮食偏好',
    prompt: '您喜欢哪些菜系？可以说多个。',
    hint: '例如：日本菜和意大利菜。没有偏好也可以直接告诉我们。',
  },
  {
    id: 'activity_styles',
    label: '旅行节奏',
    prompt: '您喜欢文化体验、冒险、轻松休闲，还是混合安排？',
    hint: '可以选择一个，也可以组合多个。',
  },
  {
    id: 'transportation',
    label: '交通偏好',
    prompt: '您更喜欢飞机、火车还是汽车？',
    hint: '可以选择一种或多种交通方式。',
  },
  {
    id: 'time_constraints',
    label: '时间或无障碍需求',
    prompt: '行程中有什么时间限制或无障碍需求需要我们注意吗？',
    hint: '如果没有，可以说“没有”。',
  },
  {
    id: 'must_go_sites',
    label: '必去景点',
    prompt: '有您一定想去的地方吗？',
    hint: '可以说一个或多个地点；如果没有，可以说“没有”。',
  },
  {
    id: 'num_people',
    label: '出行人数',
    prompt: '这次旅行一共有几个人？',
    hint: '请把您自己也计算在内。',
    required: true,
  },
]

const QUESTIONS_BY_LANGUAGE = {
  en: ENGLISH_QUESTIONS,
  zh: CHINESE_QUESTIONS,
}

const UI_COPY = {
  en: {
    eyebrow: 'OPTIONAL DYSLEXIA & READING SUPPORT',
    title: 'Voice-guided trip setup',
    description: 'The guide asks the same questions as the main form, one at a time. A final voice answer starts trip planning automatically.',
    languageLabel: 'Voice language',
    close: 'Close voice-guided trip setup',
    question: 'Question',
    of: 'of',
    complete: 'complete',
    preparing: 'Preparing voice…',
    replay: 'Replay question',
    preparingStatus: 'Preparing the voice',
    readingStatus: 'The question is being read aloud',
    voiceError: 'Voice could not play. Choose Replay question or check your browser audio settings.',
    answer: 'Your answer',
    optional: '(optional)',
    placeholder: 'Speak your answer or type it here',
    voiceAdvances: 'Speak in the selected voice language, or choose "Speak another language" to answer in Spanish, Russian, or any language — it is shown here in English. Your answer advances automatically, and missing required details stay in this guide.',
    startOver: 'Start over',
    back: 'Back',
    next: 'Next question',
    skip: 'Skip question',
    startPlanning: 'Start planning',
    starting: 'Starting your trip…',
    voiceLabel: (label) => `Answer ${label.toLowerCase()} by voice`,
    required: (label) => `Please answer ${label.toLowerCase()} before continuing. You can speak or type your answer.`,
    requiredShort: (label) => `Please answer ${label.toLowerCase()} before continuing.`,
    stillNeed: 'I still need this answer. ',
    couldNotConfirm: (labels) => `I could not confirm ${labels.join(' and ')}.`,
    repair: 'Please answer this question again. You will stay in guided setup until the required details are complete.',
    retry: (message) => `${message} Your answers have not been lost. Choose Start planning again to retry.`,
  },
  zh: {
    eyebrow: '可选的语音与阅读辅助',
    title: '语音引导式旅行设置',
    description: '我们会逐一询问与主表单相同的问题。最后一个语音回答确认后，将自动开始规划。',
    languageLabel: '语音语言',
    close: '关闭语音引导式旅行设置',
    question: '问题',
    of: '/',
    complete: '已完成',
    preparing: '正在准备语音…',
    replay: '重播问题',
    preparingStatus: '正在准备语音',
    readingStatus: '正在朗读问题',
    voiceError: '语音未能播放。请点击“重播问题”重试，或检查浏览器的音频设置。',
    answer: '您的回答',
    optional: '（可选）',
    placeholder: '请说出答案，或在这里输入',
    voiceAdvances: '请使用当前选择的语音语言回答，或点击“说其他语言”以西班牙语、俄语等任何语言回答——识别结果会以中文显示。识别完成后会自动进入下一题；缺少的必填信息会继续在这里询问。',
    startOver: '重新开始',
    back: '返回',
    next: '下一题',
    skip: '跳过此题',
    startPlanning: '开始规划',
    starting: '正在开始规划…',
    voiceLabel: (label) => `用语音回答${label}`,
    required: (label) => `请先回答“${label}”。您可以使用语音或文字输入。`,
    requiredShort: (label) => `请先回答“${label}”。`,
    stillNeed: '还需要您回答这个问题。',
    couldNotConfirm: (labels) => `无法确认以下信息：${labels.join('、')}。`,
    repair: '请再次回答这个问题。在必填信息完整之前，您会留在语音引导中。',
    retry: (message) => `${message} 您的回答仍然保留，请再次选择“开始规划”。`,
  },
}

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

function fieldLabels(language) {
  const labels = Object.fromEntries(QUESTIONS_BY_LANGUAGE[language].map(({ id, label }) => [id, label]))
  labels.budget_total = language === 'zh' ? '总预算' : 'Total budget'
  labels.currency = language === 'zh' ? '预算币种' : 'Budget currency'
  return labels
}

function answersForAssistant(answers, language) {
  const languageName = language === 'zh' ? 'Chinese' : 'English'
  const answersText = ENGLISH_QUESTIONS.map((question) => (
    `${question.label}: ${answers[question.id]?.trim() || 'None'}`
  )).join('\n')
  return `Preferred reply language: ${languageName}\n${answersText}`
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
  const [language, setLanguage] = useState('en')
  const questions = QUESTIONS_BY_LANGUAGE[language]
  const copy = UI_COPY[language]
  const question = questions[step]
  const guidedSpeech = useTextToSpeech('guided-trip-assistant', '')

  const closeGuided = useCallback(() => {
    intakeRequestVersionRef.current += 1
    guidedSpeech.stop()
    onClose()
  }, [guidedSpeech.stop, onClose])

  const speakQuestion = useCallback((prefix = '', { userInitiated = false } = {}) => {
    guidedSpeech.playText(`${prefix}${question.prompt}`, { force: true, language, userInitiated })
  }, [guidedSpeech.playText, language, question.prompt])

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
    if (direction > 0 && question.required && isMissingRequiredAnswer(answer)) {
      setError(copy.required(question.label))
      answerRef.current?.focus()
      speakQuestion(copy.stillNeed)
      return
    }
    setError('')
    setRepairMessage('')
    if (repairQuestionIds.length > 0) {
      const repairIndex = repairQuestionIds.indexOf(question.id)
      const nextRepair = repairQuestionIds[repairIndex + direction]
      if (nextRepair) {
        setStep(questions.findIndex(({ id }) => id === nextRepair))
      } else if (direction > 0) {
        reviewAnswers(answerSet)
      }
      return
    }
    setStep((current) => Math.max(0, Math.min(questions.length - 1, current + direction)))
  }

  async function reviewAnswers(answerSet = answers) {
    const answer = answerSet[question.id]?.trim() || ''
    if (question.required && isMissingRequiredAnswer(answer)) {
      setError(copy.requiredShort(question.label))
      answerRef.current?.focus()
      speakQuestion(copy.stillNeed)
      return
    }
    setStatus('loading')
    setError('')
    guidedSpeech.stop()
    const requestVersion = ++intakeRequestVersionRef.current
    try {
      const parsed = await parseTripIntake(answersForAssistant(answerSet, language), { language })
      if (requestVersion !== intakeRequestVersionRef.current || !openRef.current) return
      if (parsed.missing.length > 0) {
        const missingQuestionIds = [...new Set(parsed.missing.map((field) => FIELD_TO_QUESTION[field]).filter(Boolean))]
        const nextIndex = questions.findIndex(({ id }) => missingQuestionIds.includes(id))
        const labels = fieldLabels(language)
        const missingLabels = [...new Set(parsed.missing.map((field) => labels[field] || field))]
        setRepairMessage(copy.couldNotConfirm(missingLabels))
        setRepairQuestionIds(missingQuestionIds)
        setStep(nextIndex >= 0 ? nextIndex : 0)
        setStatus('answering')
        setError(copy.repair)
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
      setError(copy.retry(requestError.message))
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
    : step === questions.length - 1

  function changeLanguage(nextLanguage) {
    if (nextLanguage === language) return
    guidedSpeech.stop()
    setLanguage(nextLanguage)
    setError('')
    setRepairMessage('')
  }

  function isMissingRequiredAnswer(answer) {
    return !answer || ['none', '无', '没有'].includes(answer.trim().toLowerCase())
  }

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
      <header className="accessibility-panel-head" lang={language === 'zh' ? 'zh-CN' : 'en'}>
        <div>
          <span className="section-index">{copy.eyebrow}</span>
          <h2 id="guided-trip-title">{copy.title}</h2>
          <p id="guided-trip-description">{copy.description}</p>
          <div className="voice-language-switch" role="group" aria-label={copy.languageLabel}>
            <button
              type="button"
              className={language === 'en' ? 'active' : ''}
              onClick={() => changeLanguage('en')}
              aria-pressed={language === 'en'}
              lang="en"
            >
              English
            </button>
            <button
              type="button"
              className={language === 'zh' ? 'active' : ''}
              onClick={() => changeLanguage('zh')}
              aria-pressed={language === 'zh'}
              lang="zh-CN"
            >
              中文
            </button>
          </div>
        </div>
        <button ref={closeRef} className="dialog-close" type="button" onClick={closeGuided} aria-label={copy.close}>
          <X size={20} aria-hidden="true" />
        </button>
      </header>

      <div className="guided-trip-body" lang={language === 'zh' ? 'zh-CN' : 'en'}>
        <>
          <div className="guided-progress" aria-label={`${copy.question} ${step + 1} ${copy.of} ${questions.length}`}>
            <div>
              <strong>{copy.question} {step + 1} {copy.of} {questions.length}</strong>
              <span>{Math.round(((step + 1) / questions.length) * 100)}% {copy.complete}</span>
            </div>
            <progress max={questions.length} value={step + 1}>{step + 1} {copy.of} {questions.length}</progress>
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
                  onClick={() => speakQuestion('', { userInitiated: true })}
                  disabled={guidedSpeech.state === 'loading'}
                >
                  <Volume2 size={17} aria-hidden="true" />
                  {guidedSpeech.state === 'loading' ? copy.preparing : copy.replay}
                </button>
                <span className={guidedSpeech.error ? 'guided-speech-status error' : 'sr-only'} role="status" aria-live="polite">
                  {guidedSpeech.state === 'loading'
                    ? copy.preparingStatus
                    : guidedSpeech.state === 'speaking'
                      ? copy.readingStatus
                      : guidedSpeech.error
                        ? guidedSpeech.error || copy.voiceError
                        : ''}
                </span>
              </>
            )}
          </section>

          <label className="guided-description-field" htmlFor="guided-trip-answer">
            {copy.answer} {question.required ? '' : copy.optional}
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
              placeholder={copy.placeholder}
            />
            <VoiceInputButton
              autoDetect
              label={copy.voiceLabel(question.label)}
              language={language === 'zh' ? 'zh-CN' : 'en-US'}
              showText
              onTranscript={acceptVoiceAnswer}
            />
          </div>
          <p id="guided-answer-hint" className="guided-privacy">
            <ShieldCheck size={16} aria-hidden="true" />
            {copy.voiceAdvances}
          </p>
          <p id="guided-trip-error" className="guided-error" role="alert">{error}</p>
        </>
      </div>

      <footer className="accessibility-panel-actions guided-trip-actions" lang={language === 'zh' ? 'zh-CN' : 'en'}>
        <button className="reset-accessibility start-over-button" type="button" onClick={startOver}>
          <RotateCcw size={16} aria-hidden="true" /> {copy.startOver}
        </button>
        <div className="guided-step-actions">
          {canGoBack && (
            <button className="reset-accessibility" type="button" onClick={() => move(-1)}>
              <ArrowLeft size={16} aria-hidden="true" /> {copy.back}
            </button>
          )}
          {!isLastQuestion ? (
            <button className="done-accessibility" type="button" onClick={() => move(1)}>
              {currentAnswer.trim() || question.required ? copy.next : copy.skip} <ArrowRight size={16} aria-hidden="true" />
            </button>
          ) : (
            <button className="done-accessibility" type="button" onClick={() => reviewAnswers()} disabled={status === 'loading'}>
              {status === 'loading' ? copy.starting : copy.startPlanning} <Check size={16} aria-hidden="true" />
            </button>
          )}
        </div>
      </footer>
    </AccessibleDialog>
  )
}
