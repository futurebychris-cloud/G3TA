import { useState } from 'react'
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
  Users,
  Waves,
  Check,
} from 'lucide-react'
import VoiceInputButton from './accessibility/VoiceInputButton.jsx'
import GuidedTripAssistant from './GuidedTripAssistant.jsx'

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
const BUDGET_PRIORITIES = {
  balanced: {},
  comfort: { housing: 1.5 },
  food: { food: 1.5 },
  experiences: { activity: 1.5 },
  transport: { transportation: 1.5 },
}

function dateFromToday(offsetDays) {
  const date = new Date()
  date.setHours(12, 0, 0, 0)
  date.setDate(date.getDate() + offsetDays)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const FIELD_META = {
  bites: { label: 'Cuisine preferences', icon: UtensilsCrossed },
  activity_style: { label: 'Travel energy', icon: Waves },
  transportation_type: { label: 'Preferred transport', icon: PlaneTakeoff },
}

function PreferenceGroup({ field, values, selected, onToggle }) {
  const { label, icon: Icon } = FIELD_META[field]
  return (
    <fieldset className="preference-group">
      <legend><Icon size={17} /> {label}</legend>
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

export default function InputForm({ onSubmit }) {
  const [showPreferences, setShowPreferences] = useState(true)
  const [form, setForm] = useState({
    origin: 'New York',
    location: '',
    start: dateFromToday(7),
    end: dateFromToday(11),
    total: 2500,
    currency: 'USD',
    bites: [],
    transportation_type: ['flight'],
    activity_style: ['cultural', 'adventure'],
    time_constraints: 'fixed dates',
    num_people: 1,
    must_go_sites: '',
    food_budget: '',
    budget_priority: 'balanced',
  })

  function toggle(field, value) {
    setForm((current) => {
      const selected = current[field].includes(value)
      return {
        ...current,
        [field]: selected ? current[field].filter((item) => item !== value) : [...current[field], value],
      }
    })
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
        taste: form.bites,
        food_budget: form.food_budget ? Number(form.food_budget) : 0,
        budget_priority: BUDGET_PRIORITIES[form.budget_priority] || {},
      },
      time_constraints: form.time_constraints.trim(),
      must_go_sites: form.must_go_sites.split(',').map((value) => value.trim()).filter(Boolean),
      num_people: Number(form.num_people),
      is_group: Number(form.num_people) > 1,
    })
  }

  const set = (key) => (event) => setForm((current) => ({ ...current, [key]: event.target.value }))

  function applyGuidedDraft(draft) {
    setForm((current) => ({
      ...current,
      origin: draft.origin || current.origin,
      location: draft.location || current.location,
      start: draft.dates?.start || current.start,
      end: draft.dates?.end || current.end,
      total: draft.budget?.total || current.total,
      currency: draft.budget?.currency || current.currency,
      bites: draft.preferences?.bites?.length ? draft.preferences.bites : current.bites,
      transportation_type: draft.preferences?.transportation_type?.length
        ? draft.preferences.transportation_type
        : current.transportation_type,
      activity_style: draft.preferences?.activity_style?.length
        ? draft.preferences.activity_style
        : current.activity_style,
      time_constraints: draft.time_constraints || current.time_constraints,
      must_go_sites: draft.must_go_sites?.length
        ? draft.must_go_sites.join(', ')
        : current.must_go_sites,
      num_people: draft.num_people || current.num_people,
    }))
  }

  return (
    <form className="planner-card" onSubmit={submit}>
      <GuidedTripAssistant onApply={applyGuidedDraft} />
      <div className="core-fields">
        <label className="field route-field">
          <span className="field-label"><PlaneTakeoff size={15} /> Flying from</span>
          <input id="trip-origin" name="origin" autoComplete="address-level2" value={form.origin} onChange={set('origin')} placeholder="Your city" required />
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
          <PreferenceGroup field="bites" values={CUISINES} selected={form.bites} onToggle={toggle} />
          <PreferenceGroup field="activity_style" values={STYLES} selected={form.activity_style} onToggle={toggle} />
          <PreferenceGroup field="transportation_type" values={TRANSPORT} selected={form.transportation_type} onToggle={toggle} />

          <div className="trip-extra-fields">
            <label>
              <span><Users size={15} /> Travelers</span>
              <input type="number" min="1" max="100" value={form.num_people} onChange={set('num_people')} />
            </label>
            <label>
              <span>Must-go places</span>
              <input value={form.must_go_sites} onChange={set('must_go_sites')} placeholder="The Bund, Yu Garden" />
            </label>
            <label>
              <span>Food budget (optional)</span>
              <input type="number" min="0" value={form.food_budget} onChange={set('food_budget')} placeholder={form.currency} />
            </label>
            <label>
              <span>Main budget priority</span>
              <select value={form.budget_priority} onChange={set('budget_priority')}>
                <option value="balanced">Balanced</option>
                <option value="comfort">Hotel comfort</option>
                <option value="food">Food</option>
                <option value="experiences">Experiences</option>
                <option value="transport">Transportation</option>
              </select>
            </label>
          </div>

          <label className="constraint-field">
            <span><Clock3 size={16} /> Anything we should work around?</span>
            <input name="time-constraints" value={form.time_constraints} onChange={set('time_constraints')} placeholder="Flexible dates, late arrival, accessibility needs…" />
          </label>
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
