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
import VoiceInputButton from './accessibility/VoiceInputButton.jsx'
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

function dateInputValue(date) {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 10)
}

function defaultTripDates() {
  const start = new Date()
  start.setDate(start.getDate() + 30)
  const end = new Date(start)
  end.setDate(end.getDate() + 4)
  return { start: dateInputValue(start), end: dateInputValue(end) }
}

const FIELD_META = {
  bites: { label: 'Cuisine preferences', icon: UtensilsCrossed },
  activity_style: { label: 'Travel energy', icon: Waves },
  transportation_type: { label: 'Preferred transport', icon: PlaneTakeoff },
}

function PreferenceGroup({ field, values, selected, onToggle, onVoiceMatch }) {
  const { label, icon: Icon } = FIELD_META[field]
  return (
    <fieldset className="preference-group">
      <legend>
        <Icon size={17} /> {label}
        <FieldVoiceControls
          label={label}
          options={values}
          maxListenSeconds={values.length > 5 ? 5 : 3}
          onMatch={(matches) => onVoiceMatch(field, matches)}
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
    origin: 'New York',
    location: '',
    ...defaultTripDates(),
    total: 2500,
    currency: 'USD',
    bites: [],
    transportation_type: ['flight'],
    activity_style: ['cultural', 'adventure'],
    time_constraints: 'fixed dates',
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

  // Voice adds to the existing selection rather than toggling, so repeating an
  // already-selected option out loud never accidentally deselects it.
  function selectByVoice(field, matchedValues) {
    setForm((current) => ({
      ...current,
      [field]: Array.from(new Set([...current[field], ...matchedValues])),
    }))
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
        <label className="field route-field">
          <span className="field-label"><PlaneTakeoff size={15} /> Flying from</span>
          <span className="destination-input-row">
            <input id="trip-origin" name="origin" autoComplete="address-level2" value={form.origin} onChange={set('origin')} placeholder="Your city" required />
            <VoiceInputButton
              label="Enter departure city by voice"
              onTranscript={(transcript) => setForm((current) => ({ ...current, origin: transcript }))}
            />
          </span>
          <small>Departure city</small>
        </label>

        <span className="route-arrow"><ArrowRight size={18} /></span>

        <label className="field route-field destination-field">
          <span className="field-label"><MapPin size={15} /> Going to</span>
          <span className="destination-input-row">
            <input
              id="trip-destination"
              name="destination"
              autoComplete="off"
              value={form.location}
              onChange={set('location')}
              placeholder="City or country"
              required
            />
            <VoiceInputButton
              onTranscript={(transcript) => setForm((current) => ({ ...current, location: transcript }))}
            />
          </span>
          <small>City or region</small>
        </label>

        <label className="field dates-field">
          <span className="field-label"><CalendarDays size={15} /> Dates</span>
          <span className="date-pair">
            <input name="start-date" aria-label="Start date" type="date" value={form.start} onChange={set('start')} required />
            <span>→</span>
            <input name="end-date" aria-label="End date" type="date" value={form.end} onChange={set('end')} required />
          </span>
          <small>Arrival and departure</small>
        </label>

        <label className="field budget-field">
          <span className="field-label"><CircleDollarSign size={15} /> Total budget</span>
          <span className="money-input">
            <input name="currency" className="currency-input" aria-label="Currency" value={form.currency} onChange={set('currency')} maxLength={3} />
            <input name="budget" aria-label="Budget amount" type="number" min="1" value={form.total} onChange={set('total')} required />
          </span>
          <small>For the entire trip</small>
        </label>
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
          <PreferenceGroup field="bites" values={CUISINES} selected={form.bites} onToggle={toggle} onVoiceMatch={selectByVoice} />
          <PreferenceGroup field="activity_style" values={STYLES} selected={form.activity_style} onToggle={toggle} onVoiceMatch={selectByVoice} />
          <PreferenceGroup field="transportation_type" values={TRANSPORT} selected={form.transportation_type} onToggle={toggle} onVoiceMatch={selectByVoice} />

          <div className="constraint-row">
            <label className="constraint-field">
              <span><Clock3 size={16} /> Anything we should work around?</span>
              <span className="destination-input-row">
                <input name="time-constraints" value={form.time_constraints} onChange={set('time_constraints')} placeholder="Flexible dates, late arrival, accessibility needs…" />
                <VoiceInputButton
                  label="Describe timing or accessibility needs by voice"
                  onTranscript={(transcript) => setForm((current) => ({ ...current, time_constraints: transcript }))}
                />
              </span>
            </label>
            <label className="constraint-field">
              <span><Landmark size={16} /> Must-see places</span>
              <span className="destination-input-row">
                <input name="must-go-sites" value={form.must_go_sites} onChange={set('must_go_sites')} placeholder="The Bund, Yu Garden…" />
                <VoiceInputButton
                  label="Name must-see places by voice"
                  onTranscript={(transcript) => setForm((current) => ({ ...current, must_go_sites: transcript }))}
                />
              </span>
            </label>
            <label className="constraint-field party-field">
              <span><Users size={16} /> Travelers</span>
              <input name="num-people" type="number" min="1" max="100" value={form.num_people} onChange={set('num_people')} />
            </label>
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
