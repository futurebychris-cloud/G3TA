import { useEffect, useState } from 'react'
import {
  ArrowRight,
  CalendarDays,
  ChevronDown,
  CircleDollarSign,
  Clock3,
  MapPin,
  PlaneTakeoff,
  Sparkles,
  UtensilsCrossed,
  Waves,
  Check,
  Landmark,
  Users,
} from 'lucide-react'
import FieldVoiceControls from './accessibility/FieldVoiceControls.jsx'

const CUISINES = [
  'Japanese',
  'Chinese',
  'Korean',
  'Thai',
  'Indian',
  'Italian',
  'Mexican',
  'American',
  'Mediterranean',
  'French',
]
const STYLES = ['cultural', 'adventure', 'relaxed']
const TRANSPORT = ['flight', 'train', 'car']
const CURRENCIES = ['USD', 'EUR', 'GBP', 'CNY', 'JPY', 'KRW', 'AUD', 'CAD', 'SGD', 'THB']

const CURRENCY_WORDS = {
  dollar: 'USD', dollars: 'USD', usd: 'USD',
  euro: 'EUR', euros: 'EUR', eur: 'EUR',
  pound: 'GBP', pounds: 'GBP', gbp: 'GBP',
  yuan: 'CNY', rmb: 'CNY', renminbi: 'CNY', cny: 'CNY',
  yen: 'JPY', jpy: 'JPY',
  won: 'KRW', krw: 'KRW',
  baht: 'THB', thb: 'THB',
}

const NUMBER_WORDS = {
  one: 1, two: 2, three: 3, four: 4, five: 5,
  six: 6, seven: 7, eight: 8, nine: 9, ten: 10,
}

function dateInputValue(date) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 10)
}

function parseSpokenDate(text) {
  const cleaned = String(text || '')
    .trim()
    .replace(/^[\s,]*(?:from|starting|start|between|on)\b/i, '')
    .replace(/(\d+)(st|nd|rd|th)\b/gi, '$1')
    .replace(/\b(?:of|the)\b/gi, ' ')
    .replace(/[.。,!?！？]+$/g, '')
    .replace(/\s+/g, ' ')
    .trim()
  if (!cleaned) return null
  const hasYear = /\d{4}/.test(cleaned)
  const parsed = new Date(hasYear ? cleaned : `${cleaned}, ${new Date().getFullYear()}`)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

function parseSpokenDateRange(transcript) {
  const parts = String(transcript || '')
    .split(/\s*(?:\bto\b|\buntil\b|\btill\b|\bthrough\b|\band\b|–|—)\s*/i)
    .filter(Boolean)
  if (parts.length < 2) return null
  const start = parseSpokenDate(parts[0])
  let end = parseSpokenDate(parts[1])
  // "August 23 to 27" — bare day number borrows the start's month/year.
  const bareDay = parts[1].trim().replace(/[.。,!?！？]+$/g, '').match(/^(\d{1,2})$/)
  if (start && !end && bareDay) {
    end = new Date(start)
    end.setDate(Number(bareDay[1]))
  }
  if (!start || !end) return null
  return { start: dateInputValue(start), end: dateInputValue(end) }
}

function parseSpokenBudget(transcript) {
  const text = String(transcript || '').toLowerCase().replace(/,/g, '')
  const numberMatch = text.match(/\d+(?:\.\d+)?/)
  let amount = numberMatch ? Number(numberMatch[0]) : null
  if (amount != null && /\bthousand\b/.test(text)) amount *= 1000
  let currency = null
  for (const [word, code] of Object.entries(CURRENCY_WORDS)) {
    if (new RegExp(`\\b${word}\\b`).test(text)) { currency = code; break }
  }
  return { amount, currency }
}

function parseSpokenCount(transcript) {
  const text = String(transcript || '').toLowerCase()
  const digits = text.match(/\d+/)
  if (digits) return Number(digits[0])
  for (const [word, value] of Object.entries(NUMBER_WORDS)) {
    if (new RegExp(`\\b${word}\\b`).test(text)) return value
  }
  return null
}

const FIELD_META = {
  bites: { label: 'Cuisine preferences', icon: UtensilsCrossed },
  activity_style: { label: 'Travel energy', icon: Waves },
  transportation_type: { label: 'Preferred transport', icon: PlaneTakeoff },
}

function PreferenceGroup({ field, values, selected, onToggle, onVoiceMatch, onVoiceStart }) {
  const { label, icon: Icon } = FIELD_META[field]
  return (
    <fieldset className="preference-group">
      <legend>
        <Icon size={17} /> {label}
        <FieldVoiceControls
          label={label}
          options={values}
          listenSeconds={values.length > 5 ? 5 : 3}
          onMatch={(matches) => onVoiceMatch(field, matches)}
          onSpeakStart={() => onVoiceStart(field)}
        />
      </legend>
      {field === 'bites' && <p className="preference-hint">Choose in priority order. Your first choice is treated as primary.</p>}
      <div className="choice-list">
        {values.map((value) => (
          <button
            type="button"
            key={value}
            className={selected.includes(value) ? 'choice-chip selected' : 'choice-chip'}
            onClick={() => onToggle(field, value)}
            aria-pressed={selected.includes(value)}
          >
            <span className="choice-check" aria-hidden="true">
              {selected.includes(value) && <Check size={11} />}
            </span>
            {value}
            <span className="sr-only">{selected.includes(value) ? ' selected' : ' not selected'}</span>
          </button>
        ))}
      </div>
    </fieldset>
  )
}

export default function InputForm({ onSubmit, intakeDraft, intakeNotice }) {
  const [showPreferences, setShowPreferences] = useState(true)
  const [form, setForm] = useState(() => ({
    origin: '',
    location: '',
    start: '',
    end: '',
    total: '',
    currency: 'USD',
    bites: [],
    transportation_type: [],
    activity_style: [],
    time_constraints: '',
    must_go_sites: '',
    num_people: 1,
  }))

  useEffect(() => {
    if (!intakeDraft) return
    setForm({
      origin: intakeDraft.origin || '',
      location: intakeDraft.location || '',
      start: intakeDraft.dates?.start || '',
      end: intakeDraft.dates?.end || '',
      total: intakeDraft.budget?.total || '',
      currency: intakeDraft.budget?.currency || 'USD',
      bites: intakeDraft.preferences?.bites || [],
      transportation_type: intakeDraft.preferences?.transportation_type || [],
      activity_style: intakeDraft.preferences?.activity_style || [],
      time_constraints: intakeDraft.time_constraints || '',
      must_go_sites: (intakeDraft.must_go_sites || []).join(', '),
      num_people: intakeDraft.num_people || 1,
    })
    const hasPreferences = Boolean(
      intakeDraft.preferences?.bites?.length
      || intakeDraft.preferences?.transportation_type?.length
      || intakeDraft.preferences?.activity_style?.length
      || intakeDraft.time_constraints
      || intakeDraft.must_go_sites?.length,
    )
    setShowPreferences(hasPreferences)
  }, [intakeDraft])

  function toggle(field, value) {
    setForm((current) => {
      const selected = current[field].includes(value)
      return {
        ...current,
        [field]: selected ? current[field].filter((item) => item !== value) : [...current[field], value],
      }
    })
  }

  // A fresh "speak" wipes the field's previous selection, then the transcript's
  // matches become the new selection — saying several options checks them all.
  function clearChoices(field) {
    setForm((current) => ({ ...current, [field]: [] }))
  }

  function selectByVoice(field, matchedValues) {
    setForm((current) => ({ ...current, [field]: matchedValues }))
  }

  const setValue = (key) => (value) => setForm((current) => ({ ...current, [key]: value }))

  // Whisper punctuates transcripts ("London.") — strip trailing punctuation for
  // short name-like fields where it doesn't belong.
  const setSpokenName = (key) => (value) => setForm((current) => ({
    ...current,
    [key]: String(value || '').trim().replace(/[.。,，!！?？]+$/u, ''),
  }))

  // Each date has its own speak button (far more reliable than range parsing),
  // but if someone speaks a full range to either one, both fields fill.
  // Returns false when nothing parsed so the mic can flash its error state.
  const fillOneDateByVoice = (key) => (transcript) => {
    const range = parseSpokenDateRange(transcript)
    if (range) {
      setForm((current) => ({ ...current, start: range.start, end: range.end }))
      return true
    }
    const single = parseSpokenDate(String(transcript).replace(/[.。,!?！？]+$/g, ''))
    if (single) {
      setForm((current) => ({ ...current, [key]: dateInputValue(single) }))
      return true
    }
    return false
  }

  function fillBudgetByVoice(transcript) {
    const { amount, currency } = parseSpokenBudget(transcript)
    setForm((current) => ({
      ...current,
      ...(amount != null ? { total: amount } : {}),
      ...(currency ? { currency } : {}),
    }))
  }

  function fillTravelersByVoice(transcript) {
    const count = parseSpokenCount(transcript)
    if (count != null && count >= 1 && count <= 100) {
      setForm((current) => ({ ...current, num_people: count }))
    }
  }

  function submit(event) {
    event.preventDefault()
    onSubmit({
      location: form.location.trim(),
      origin: form.origin.trim(),
      dates: { start: form.start, end: form.end },
      budget: { total: Number(form.total), currency: form.currency.trim().toUpperCase() },
      preferences: {
        bites: form.bites,
        transportation_type: form.transportation_type,
        activity_style: form.activity_style,
      },
      time_constraints: form.time_constraints.trim(),
      must_go_sites: form.must_go_sites
        .split(/[,\n]/)
        .map((site) => site.trim())
        .filter(Boolean),
      num_people: Number(form.num_people),
      is_group: Number(form.num_people) >= 5,
    })
  }

  const set = (key) => (event) => setForm((current) => ({ ...current, [key]: event.target.value }))

  return (
    <form className="planner-card" onSubmit={submit}>
      {intakeDraft && (
        <div className="intake-draft-banner" role="status">
          <Sparkles size={20} aria-hidden="true" />
          <div>
            <strong>Your guided draft is in the normal form</strong>
            <p>{intakeNotice?.summary || 'Review every detail below, complete anything missing, then choose Design my journey.'}</p>
            {intakeNotice?.missing?.length > 0 && <small>Some details still need your input. Empty required fields are shown below.</small>}
          </div>
        </div>
      )}
      <div className="core-fields">
        <div className="field route-field">
          <span className="field-label">
            <PlaneTakeoff size={15} /> <label htmlFor="trip-origin">Flying from</label>
            <FieldVoiceControls
              label="Flying from"
              readText="Flying from. Say your departure city."
              onText={setSpokenName('origin')}
            />
          </span>
          <input id="trip-origin" name="origin" autoComplete="address-level2" value={form.origin} onChange={set('origin')} placeholder="Your city" required />
          <small>Departure city</small>
        </div>

        <span className="route-arrow"><ArrowRight size={18} /></span>

        <div className="field route-field destination-field">
          <span className="field-label">
            <MapPin size={15} /> <label htmlFor="trip-destination">Going to</label>
            <FieldVoiceControls
              label="Going to"
              readText="Going to. Say the city or country you want to visit."
              onText={setSpokenName('location')}
            />
          </span>
          <input
            id="trip-destination"
            name="destination"
            autoComplete="off"
            value={form.location}
            onChange={set('location')}
            placeholder="City or country"
            required
          />
          <small>City or region</small>
        </div>

        <div className="field dates-field">
          <span className="field-label">
            <CalendarDays size={15} /> Dates
          </span>
          <span className="date-pair">
            <span className="date-col">
              <input name="start-date" aria-label="Start date" type="date" value={form.start} onChange={set('start')} required />
              <span className="date-col-foot">
                <small>Arrival</small>
                <FieldVoiceControls
                  label="Arrival date"
                  readText="Arrival date. Say the date, for example: August 23rd."
                  listenSeconds={4}
                  onText={fillOneDateByVoice('start')}
                />
              </span>
            </span>
            <span className="date-col">
              <input name="end-date" aria-label="End date" type="date" value={form.end} onChange={set('end')} required />
              <span className="date-col-foot">
                <small>Departure</small>
                <FieldVoiceControls
                  label="Departure date"
                  readText="Departure date. Say the date, for example: August 27th."
                  listenSeconds={4}
                  onText={fillOneDateByVoice('end')}
                />
              </span>
            </span>
          </span>
        </div>

        <div className="field budget-field">
          <span className="field-label">
            <CircleDollarSign size={15} /> Total budget
            <FieldVoiceControls
              label="Total budget"
              readText={`Total budget. Say the amount and currency, for example: 2500 US dollars. Currency options are: ${CURRENCIES.join(', ')}.`}
              listenSeconds={5}
              onText={fillBudgetByVoice}
            />
          </span>
          <span className="money-input">
            <select name="currency" className="currency-select" aria-label="Currency" value={form.currency} onChange={set('currency')}>
              {CURRENCIES.map((code) => <option key={code} value={code}>{code}</option>)}
            </select>
            <input name="budget" aria-label="Budget amount" type="number" min="1" value={form.total} onChange={set('total')} placeholder="Amount" required />
          </span>
          <small>For the entire trip</small>
        </div>
      </div>

      <button
        type="button"
        className={showPreferences ? 'preference-toggle open' : 'preference-toggle'}
        onClick={() => setShowPreferences((open) => !open)}
        aria-expanded={showPreferences}
        aria-controls="trip-preferences"
      >
        <span><Sparkles size={16} /> Personalize this journey</span>
        <span className="preference-summary">{form.bites.length + form.activity_style.length + form.transportation_type.length} preferences</span>
        <ChevronDown size={18} />
      </button>

      {showPreferences && (
        <div className="preferences-panel" id="trip-preferences">
          <PreferenceGroup field="bites" values={CUISINES} selected={form.bites} onToggle={toggle} onVoiceMatch={selectByVoice} onVoiceStart={clearChoices} />
          <PreferenceGroup field="activity_style" values={STYLES} selected={form.activity_style} onToggle={toggle} onVoiceMatch={selectByVoice} onVoiceStart={clearChoices} />
          <PreferenceGroup field="transportation_type" values={TRANSPORT} selected={form.transportation_type} onToggle={toggle} onVoiceMatch={selectByVoice} onVoiceStart={clearChoices} />

          <div className="constraint-row">
            <div className="constraint-field">
              <span>
                <Clock3 size={16} /> <label htmlFor="time-constraints">Anything we should work around?</label>
                <FieldVoiceControls
                  label="Anything we should work around"
                  readText="Anything we should work around? For example: flexible dates, late arrival, or accessibility needs."
                  listenSeconds={5}
                  onText={setValue('time_constraints')}
                />
              </span>
              <input id="time-constraints" name="time-constraints" value={form.time_constraints} onChange={set('time_constraints')} placeholder="Flexible dates, late arrival, accessibility needs…" />
            </div>
            <div className="constraint-field">
              <span>
                <Landmark size={16} /> <label htmlFor="must-go-sites">Must-see places</label>
                <FieldVoiceControls
                  label="Must-see places"
                  readText="Must-see places. Name one or more places you don't want to miss."
                  listenSeconds={5}
                  onText={setSpokenName('must_go_sites')}
                />
              </span>
              <input id="must-go-sites" name="must-go-sites" value={form.must_go_sites} onChange={set('must_go_sites')} placeholder="The Bund, Yu Garden…" />
            </div>
            <div className="constraint-field party-field">
              <span>
                <Users size={16} /> <label htmlFor="num-people">Travelers</label>
                <FieldVoiceControls
                  label="Travelers"
                  readText="Travelers. Say how many people are going, including yourself."
                  onText={fillTravelersByVoice}
                />
              </span>
              <input id="num-people" name="num-people" type="number" min="1" max="100" value={form.num_people} onChange={set('num_people')} />
            </div>
          </div>
        </div>
      )}

      <div className="planner-action">
        <div className="agent-avatars" aria-hidden="true">
          {['B', 'T', 'H', 'F', 'A', 'P'].map((agent, index) => <span key={agent} style={{ '--i': index }}>{agent}</span>)}
          <small>6 agents ready</small>
        </div>
        <button type="submit" className="plan-button">
          Design my journey <ArrowRight size={19} />
        </button>
      </div>
    </form>
  )
}
