import { useState } from 'react'
import { Check, CloudSun, Luggage, TimerReset } from 'lucide-react'

export default function PackingList({ items, weather, pacing }) {
  const [checked, setChecked] = useState(() => new Set())

  function toggle(index) {
    setChecked((current) => {
      const next = new Set(current)
      if (next.has(index)) next.delete(index)
      else next.add(index)
      return next
    })
  }

  return (
    <div className="packing-view">
      <div className="panel-heading">
        <div><span className="section-index">READY, SET</span><h2>Pack light.<br />Arrive prepared.</h2></div>
        <p>A practical list shaped by the forecast, your plans, and the way you like to travel.</p>
      </div>

      <div className="travel-advisories">
        <article className="advisory weather-advisory">
          <span className="advisory-icon"><CloudSun size={25} /></span>
          <div><span className="section-index">WEATHER OUTLOOK</span><p>{weather}</p></div>
        </article>
        <article className="advisory pacing-advisory">
          <span className="advisory-icon"><TimerReset size={25} /></span>
          <div><span className="section-index">PACING NOTE</span><p>{pacing}</p></div>
        </article>
      </div>

      <section className="packing-checklist">
        <div className="packing-head">
          <div><Luggage size={20} /><h3>Travel checklist</h3></div>
          <span>{checked.size} of {items.length} packed</span>
        </div>
        <div className="packing-progress"><span style={{ width: `${(checked.size / Math.max(items.length, 1)) * 100}%` }} /></div>
        <div className="packing-grid">
          {items.map((item, index) => (
            <label className={checked.has(index) ? 'packing-item packed' : 'packing-item'} key={`${item}-${index}`}>
              <input type="checkbox" checked={checked.has(index)} onChange={() => toggle(index)} />
              <span className="packing-checkbox"><Check size={14} /></span>
              <span><small>{String(index + 1).padStart(2, '0')}</small>{item}</span>
            </label>
          ))}
        </div>
      </section>
    </div>
  )
}
