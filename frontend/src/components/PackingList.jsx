import { useState, useEffect, useCallback } from 'react'
import { Check, CloudDrizzle, CloudRain, CloudSun, Luggage, Sun, TimerReset, Umbrella, Wind } from 'lucide-react'
import { getChecklist, toggleChecklistItem } from '../api.js'

function weatherIcon(condition, size = 18) {
  const c = (condition || '').toLowerCase()
  if (c.includes('rain') || c.includes('drizzle')) return <CloudRain size={size} />
  if (c.includes('cloud') || c.includes('overcast')) return <CloudDrizzle size={size} />
  if (c.includes('fog')) return <Wind size={size} />
  if (c.includes('snow')) return <CloudSnow size={size} />
  if (c.includes('thunder')) return <CloudRain size={size} />
  return <Sun size={size} />
}

function formatDate(dateStr) {
  try {
    return new Date(`${dateStr}T00:00:00`).toLocaleDateString('en', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    })
  } catch {
    return dateStr
  }
}

/** Normalize an item string like "[clothing] Warm jacket" so we can match it to DB items. */
function normalizeItemName(itemStr) {
  // Strip category prefix "[clothing] " if present
  return itemStr.replace(/^\[.*?\]\s*/, '').trim()
}

export default function PackingList({ items, weather, pacing, dailyWeather, healthAdvice, tripId }) {
  const [checked, setChecked] = useState(() => new Set())
  const [dbItemMap, setDbItemMap] = useState(null) // null = loading, Map<itemName, {id, is_packed}> | null on error

  // Fetch checklist from shared_checklist DB to restore packed/unpacked state.
  useEffect(() => {
    if (!tripId) return
    let cancelled = false
    getChecklist(tripId).then((data) => {
      if (cancelled) return
      const map = new Map()
      for (const row of data.items || []) {
        map.set(row.item_name, { id: row.id, is_packed: row.is_packed === 1 })
      }
      setDbItemMap(map)

      // Initialize checked set from DB
      setChecked(() => {
        const dbChecked = new Set()
        items.forEach((item, index) => {
          const name = normalizeItemName(item)
          const db = map.get(name)
          if (db && db.is_packed) dbChecked.add(index)
        })
        return dbChecked
      })
    }).catch((err) => {
      if (!cancelled) {
        console.warn('[PackingList] failed to sync from DB:', err)
        setDbItemMap(null) // fall back to local-only
      }
    })
    return () => { cancelled = true }
  }, [tripId]) // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = useCallback((index) => {
    setChecked((current) => {
      const next = new Set(current)
      if (next.has(index)) {
        next.delete(index)
        // Persist unpack to backend
        const name = normalizeItemName(items[index])
        const db = dbItemMap?.get(name)
        if (db) toggleChecklistItem(db.id, tripId, false).catch(() => {})
      } else {
        next.add(index)
        // Persist packed to backend
        const name = normalizeItemName(items[index])
        const db = dbItemMap?.get(name)
        if (db) toggleChecklistItem(db.id, tripId, true).catch(() => {})
      }
      return next
    })
  }, [items, dbItemMap, tripId])

  const hasDailyWeather = dailyWeather && dailyWeather.length > 0

  return (
    <div className="packing-view">
      <div className="panel-heading">
        <div><span className="section-index">READY, SET</span><h2>Pack light.<br />Arrive prepared.</h2></div>
        <p>A practical list shaped by the forecast, your plans, and the way you like to travel.</p>
      </div>

      {/* Weather outlook */}
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

      {/* Daily weather cards */}
      {hasDailyWeather && (
        <section className="daily-weather-section">
          <div className="section-header">
            <div>
              <span className="section-index">DAY-BY-DAY FORECAST</span>
              <h3>What to expect each day</h3>
            </div>
            <span className="weather-source">
              <CloudSun size={14} /> Open-Meteo (real forecast)
            </span>
          </div>
          <div className="daily-weather-grid">
            {dailyWeather.map((day, idx) => (
              <div key={day.date || idx} className="daily-weather-card">
                <div className="dw-date">
                  <span className="dw-day">{formatDate(day.date)}</span>
                  <span className="dw-condition">
                    {weatherIcon(day.condition)}
                    {day.condition || 'Unknown'}
                  </span>
                </div>
                <div className="dw-temps">
                  <span className="dw-high">{day.high_c != null ? `${Math.round(day.high_c)}°` : '—'}</span>
                  <span className="dw-sep">/</span>
                  <span className="dw-low">{day.low_c != null ? `${Math.round(day.low_c)}°` : '—'}</span>
                </div>
                <div className="dw-details">
                  {day.rain_chance != null && day.rain_chance > 0 && (
                    <span className="dw-rain">
                      <Umbrella size={11} />
                      {Math.round(day.rain_chance * 100)}%
                    </span>
                  )}
                  {day.precipitation_mm != null && day.precipitation_mm > 0 && (
                    <span className="dw-precip">{day.precipitation_mm}mm</span>
                  )}
                </div>
                {day.rain_chance != null && day.rain_chance > 0.3 && (
                  <div className="dw-bar" style={{ width: `${Math.min(day.rain_chance * 100, 100)}%` }} />
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Health advisory */}
      {healthAdvice && (
        <section className="health-advisory-section">
          <div className="advisory health-advisory-card">
            <span className="advisory-icon"><Luggage size={20} /></span>
            <div>
              <span className="section-index">HEALTH ADVISORY</span>
              <p>{healthAdvice}</p>
            </div>
          </div>
        </section>
      )}

      {/* Packing checklist */}
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

// Snow icon helper
function CloudSnow(props) {
  return (
    <svg {...props} xmlns="http://www.w3.org/2000/svg" width={props.size || 24} height={props.size || 24} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z" />
      <path d="M8 12h.01" /><path d="M12 12h.01" /><path d="M16 12h.01" />
      <path d="M8 16h.01" /><path d="M12 16h.01" /><path d="M16 16h.01" />
    </svg>
  )
}
