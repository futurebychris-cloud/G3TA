import { useState } from 'react'

// Trip input form (PRD §6 / §9 step 1). Pre-filled with the Tokyo demo scenario
// so the presenter can plan in one click, but every field is editable.
const CUISINES = ['ramen', 'sushi', 'izakaya', 'street food', 'tempura', 'vegan', 'cafe']
const STYLES = ['cultural', 'adventure', 'relaxed']
const TRANSPORT = ['flight', 'train', 'car']

export default function InputForm({ onSubmit }) {
  const [form, setForm] = useState({
    origin: 'New York',
    location: 'Tokyo',
    start: '2026-04-10',
    end: '2026-04-14',
    total: 2500,
    currency: 'USD',
    bites: ['ramen', 'sushi'],
    transportation_type: ['flight'],
    activity_style: ['cultural', 'adventure'],
    time_constraints: 'fixed dates',
  })

  function toggle(field, value) {
    setForm((f) => {
      const has = f[field].includes(value)
      return { ...f, [field]: has ? f[field].filter((v) => v !== value) : [...f[field], value] }
    })
  }

  function submit(e) {
    e.preventDefault()
    onSubmit({
      location: form.location,
      origin: form.origin,
      dates: { start: form.start, end: form.end },
      budget: { total: Number(form.total), currency: form.currency },
      preferences: {
        bites: form.bites,
        transportation_type: form.transportation_type,
        activity_style: form.activity_style,
      },
      time_constraints: form.time_constraints,
    })
  }

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  return (
    <form className="card form" onSubmit={submit}>
      <div className="row">
        <label>
          From
          <input value={form.origin} onChange={set('origin')} placeholder="Origin city" />
        </label>
        <label>
          Destination
          <input value={form.location} onChange={set('location')} required />
        </label>
      </div>

      <div className="row">
        <label>
          Start date
          <input type="date" value={form.start} onChange={set('start')} required />
        </label>
        <label>
          End date
          <input type="date" value={form.end} onChange={set('end')} required />
        </label>
      </div>

      <div className="row">
        <label>
          Total budget
          <input type="number" min="0" value={form.total} onChange={set('total')} required />
        </label>
        <label>
          Currency
          <input value={form.currency} onChange={set('currency')} />
        </label>
      </div>

      <fieldset>
        <legend>Cuisine preferences</legend>
        <div className="chips">
          {CUISINES.map((c) => (
            <button type="button" key={c} className={form.bites.includes(c) ? 'chip on' : 'chip'} onClick={() => toggle('bites', c)}>
              {c}
            </button>
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend>Activity style</legend>
        <div className="chips">
          {STYLES.map((s) => (
            <button type="button" key={s} className={form.activity_style.includes(s) ? 'chip on' : 'chip'} onClick={() => toggle('activity_style', s)}>
              {s}
            </button>
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend>Transportation</legend>
        <div className="chips">
          {TRANSPORT.map((t) => (
            <button type="button" key={t} className={form.transportation_type.includes(t) ? 'chip on' : 'chip'} onClick={() => toggle('transportation_type', t)}>
              {t}
            </button>
          ))}
        </div>
      </fieldset>

      <label>
        Time constraints
        <input value={form.time_constraints} onChange={set('time_constraints')} placeholder="e.g. flexible, fixed dates" />
      </label>

      <button type="submit" className="primary">Plan my trip →</button>
    </form>
  )
}
