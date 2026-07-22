import { useState } from 'react'
import { Check, CloudSun, Luggage, TimerReset } from 'lucide-react'
import { useAccessibilitySettings } from '../accessibility/AccessibilityContext.jsx'
import LineFocusReader from './accessibility/LineFocusReader.jsx'
import ReadAloudButton from './accessibility/ReadAloudButton.jsx'

export default function PackingList({ items, weather, pacing }) {
  const [checked, setChecked] = useState(() => new Set())
  const [showAll, setShowAll] = useState(false)
  const { settings } = useAccessibilitySettings()
  const isSenior = settings.preset === 'senior'
  const visibleItems = isSenior && !showAll ? items.slice(0, 6) : items

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
      <div className="result-heading-actions">
        <ReadAloudButton id="packing-summary" label="weather, pacing, and packing list" text={[weather, pacing, ...items]} />
      </div>

      <div className="travel-advisories">
        <article className="advisory weather-advisory" aria-labelledby="weather-outlook-heading">
          <span className="advisory-icon" aria-hidden="true"><CloudSun size={25} /></span>
          <div><h3 className="section-index" id="weather-outlook-heading">Weather outlook</h3><LineFocusReader text={weather} /></div>
        </article>
        <article className="advisory pacing-advisory" aria-labelledby="pacing-note-heading">
          <span className="advisory-icon" aria-hidden="true"><TimerReset size={25} /></span>
          <div><h3 className="section-index" id="pacing-note-heading">Pacing note</h3><LineFocusReader text={pacing} /></div>
        </article>
      </div>

      <section className="packing-checklist">
        <div className="packing-head">
          <div><Luggage size={20} /><h3>Travel checklist</h3></div>
          <span role="status" aria-live="polite">{checked.size} of {items.length} packed</span>
        </div>
        <div className="packing-progress" role="progressbar" aria-label="Packing progress" aria-valuenow={checked.size} aria-valuemin="0" aria-valuemax={items.length}><span style={{ width: `${(checked.size / Math.max(items.length, 1)) * 100}%` }} /></div>
        <div className="packing-grid">
          {visibleItems.map((item, index) => (
            <label className={checked.has(index) ? 'packing-item packed' : 'packing-item'} key={`${item}-${index}`}>
              <input type="checkbox" checked={checked.has(index)} onChange={() => toggle(index)} />
              <span className="packing-checkbox" aria-hidden="true"><Check size={14} /></span>
              <span><small>{String(index + 1).padStart(2, '0')}</small>{item}</span>
            </label>
          ))}
        </div>
        {isSenior && items.length > 6 && (
          <button className="show-more-results" type="button" aria-expanded={showAll} onClick={() => setShowAll((current) => !current)}>
            {showAll ? 'Show fewer packing items' : `Show all ${items.length} packing items`}
          </button>
        )}
      </section>
    </div>
  )
}
