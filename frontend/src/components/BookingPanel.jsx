import { useMemo, useState } from 'react'
import { BedDouble, Check, ExternalLink, LoaderCircle, MapPin, RefreshCw, Search, ShieldAlert, Star, ImageOff, Info, Sparkles, Bath, Coffee, Wifi, Tv, Wind, Car, Dumbbell, Waves, UtensilsCrossed } from 'lucide-react'
import { streamBookingSearch } from '../api.js'

const STAGES = [
  { key: 'search', label: 'Search', note: 'Querying the currently configured hotel sources', icon: Search },
  { key: 'filtering', label: 'Filtering', note: 'Dropping above budget / below rating, ranking', icon: Check },
  { key: 'outputting', label: 'Outputting', note: 'Compiling your shortlist of stays', icon: BedDouble },
]

const SOURCE_LABEL = {
  api: 'Configured hotel API',
  ctrip: 'Ctrip (携程) public listing',
  openstreetmap: 'OpenStreetMap place record (price unavailable)',
  mock: 'Offline demo data (not live)',
}

// Map Chinese/English label keywords to Lucide icons
const LABEL_ICONS = {
  'bathtub': Bath, '浴缸': Bath, 'bath': Bath,
  'breakfast': Coffee, '含早餐': Coffee, '早餐': Coffee, 'meal': Coffee,
  'wifi': Wifi, 'wi-fi': Wifi, '无线': Wifi, 'internet': Wifi,
  'tv': Tv, '电视': Tv, 'television': Tv,
  'air conditioning': Wind, '空调': Wind, 'ac': Wind,
  'parking': Car, '停车': Car, '停车场': Car,
  'gym': Dumbbell, '健身房': Dumbbell, '健身': Dumbbell, 'fitness': Dumbbell,
  'pool': Waves, '泳池': Waves, '游泳池': Waves, 'swimming': Waves,
  'restaurant': UtensilsCrossed, '餐厅': UtensilsCrossed, '餐饮': UtensilsCrossed,
  'washing': Sparkles, '洗衣机': Sparkles, '洗衣': Sparkles, 'laundry': Sparkles,
  'washing machine': Sparkles,
  'spa': Sparkles, '水疗': Sparkles,
}

function labelIcon(label) {
  const key = label.toLowerCase()
  for (const [k, Icon] of Object.entries(LABEL_ICONS)) {
    if (key.includes(k)) return Icon
  }
  return null
}

function nightsBetween(start, end) {
  const d0 = new Date(`${start}T00:00:00`)
  const d1 = new Date(`${end}T00:00:00`)
  return Math.max(1, Math.round((d1 - d0) / 86400000))
}

export default function BookingPanel({ trip }) {
  const nights = useMemo(
    () => nightsBetween(trip.dates.start, trip.dates.end),
    [trip.dates.start, trip.dates.end],
  )
  const suggestedCap = useMemo(() => {
    const cur = (trip.budget || {}).currency
    if (cur === 'CNY' || cur === 'USD') return Math.round((trip.budget?.total || 0) / nights)
    return undefined
  }, [trip.budget, nights])

  const [cap, setCap] = useState(suggestedCap ? String(suggestedCap) : '')
  const [stages, setStages] = useState(Object.fromEntries(STAGES.map((s) => [s.key, 'pending'])))
  const [source, setSource] = useState(null)
  const [hotels, setHotels] = useState([])
  const [error, setError] = useState(null)
  const [searching, setSearching] = useState(false)

  const [selected, setSelected] = useState(null)

  async function runSearch() {
    setError(null)
    setHotels([])
    setSelected(null)
    setSource(null)
    setStages(Object.fromEntries(STAGES.map((s) => [s.key, 'pending'])))
    setSearching(true)
    setStages((s) => ({ ...s, search: 'running' }))
    try {
      const req = {
        location: trip.location,
        check_in: trip.dates.start,
        check_out: trip.dates.end,
        adults: trip.num_people || 1,
        children: 0,
        rooms: Math.max(1, Math.ceil((trip.num_people || 1) / 2)),
        max_price_per_night: cap ? Number(cap) : undefined,
        preferences: (Array.isArray(trip.preferences)
          ? trip.preferences
          : Object.values(trip.preferences || {}).flat()
        ).map(String),
      }
      await streamBookingSearch(req, (evt) => {
        if (evt.type === 'booking_stage') {
          setStages((s) => ({ ...s, [evt.stage]: evt.status }))
          if (evt.source) setSource(evt.source)
        } else if (evt.type === 'booking_results') {
          setHotels(evt.hotels)
        } else if (evt.type === 'error') {
          setError(evt.message)
        }
      })
    } catch (e) {
      setError(e.message)
    } finally {
      setSearching(false)
    }
  }

  return (
    <div className="booking-panel">
      <div className="panel-heading">
        <div>
          <span className="section-index">COMPARE YOUR STAY</span>
          <h2>Research here.<br />Book with the provider.</h2>
        </div>
        <p>
          Search configured hotel providers, Ctrip, then OpenStreetMap. Prices and
          availability can change; G3TA never marks a stay paid or confirmed without
          provider proof.
        </p>
      </div>

      <div className="booking-controls">
        <label className="cap-field">
          <span>Max price / night (optional)</span>
          <input
            type="number"
            value={cap}
            placeholder={suggestedCap ? `suggested ${suggestedCap}` : 'any'}
            onChange={(e) => setCap(e.target.value)}
          />
        </label>
        <button className="text-button" onClick={runSearch} disabled={searching}>
          <RefreshCw size={15} className={searching ? 'spin' : ''} /> {searching ? 'Searching…' : hotels.length ? 'Search again' : 'Search stays'}
        </button>
      </div>

      <ol className="agent-list booking-stages">
        {STAGES.map((s) => {
          const status = stages[s.key] || 'pending'
          const Icon = s.icon
          return (
            <li key={s.key} className={`agent-row ${status}`}>
              <span className="agent-icon"><Icon size={18} strokeWidth={1.8} /></span>
              <span className="agent-copy"><strong>{s.label}</strong><small>{s.note}</small></span>
              <span className="agent-state">
                {status === 'done' && <><Check size={15} /> Complete</>}
                {status === 'running' && <><LoaderCircle className="spinner" size={15} /> Working</>}
                {status === 'pending' && 'Queued'}
              </span>
            </li>
          )
        })}
      </ol>

      {source && (
        <div className="source-note">
          <ShieldAlert size={15} /> Source: <strong>{SOURCE_LABEL[source] || source}</strong>
          {source === 'openstreetmap' && ' — live prices aren’t published here; confirm the rate on the provider.'}
        </div>
      )}

      {error && (
        <div className="progress-error" role="alert">
          <strong>Booking search paused.</strong>
          <p>{error}</p>
          <button type="button" onClick={runSearch}><RefreshCw size={16} /> Try again</button>
        </div>
      )}

      {hotels.length > 0 && (
        <div className="hotel-grid">
          {hotels.map((h) => {
            const hasImage = h.images?.length > 0
            const hasMap = h.lat != null && h.lng != null
            const hasRooms = h.rooms?.length > 0
            const hasLabels = h.labels?.length > 0
            const showDescription = h.description?.length > 20

            return (
            <article
              key={h.id}
              className={`hotel-card ${selected?.id === h.id ? 'selected' : ''}`}
              onClick={() => setSelected(h)}
            >
              {/* Hotel image */}
              {hasImage ? (
                <div className="hotel-image">
                  <img
                    src={h.images[0]}
                    alt={h.name}
                    loading="lazy"
                    onError={(e) => { e.target.style.display = 'none' }}
                  />
                </div>
              ) : (
                <div className="hotel-image hotel-image-placeholder">
                  <ImageOff size={28} />
                </div>
              )}

              <div className="hotel-card-head">
                <h4>{h.name}</h4>
                <span className={`src-badge ${h.source}`}>{SOURCE_LABEL[h.source] || h.source}</span>
              </div>

              {/* Star rating */}
              {h.star_rating != null && (
                <div className="hotel-stars">
                  <Star size={14} fill="var(--sand)" stroke="var(--sand)" />
                  <span>{h.star_rating} stars</span>
                </div>
              )}

              <div className="hotel-meta">
                {h.rating != null && <span className="rating">★ {h.rating}</span>}
                {h.area && <span className="area">{h.area}</span>}
              </div>

              {/* Description */}
              {showDescription && (
                <div className="hotel-desc">
                  <Info size={12} />
                  <span>{h.description.slice(0, 120)}{h.description.length > 120 ? '…' : ''}</span>
                </div>
              )}

              {/* Map links */}
              {hasMap && (
                <div className="hotel-map-links">
                  <MapPin size={13} />
                  <a
                    href={`https://uri.amap.com/marker?position=${h.lng},${h.lat}&name=${encodeURIComponent(h.name)}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                  >
                    Open in AMap 高德地图
                  </a>
                </div>
              )}

              {/* Price & cost breakdown */}
              <div className="hotel-price">
                {h.price_per_night != null ? (
                  <>
                    <strong>{h.price_per_night}</strong> {h.currency}/night
                    {h.total_cost != null && h.total_cost !== h.price_per_night && (
                      <span className="total-cost">
                        {h.total_cost} {h.currency} total · {nights} nights
                      </span>
                    )}
                    {h.discount != null && h.discount > 0 && (
                      <span className="discount-badge">-{h.discount} {h.currency}</span>
                    )}
                  </>
                ) : (
                  <span className="no-price">Price to confirm on provider</span>
                )}
              </div>

              {/* Amenity labels with icons */}
              {hasLabels && (
                <div className="hotel-labels">
                  {h.labels.slice(0, 8).map((lbl) => {
                    const Icon = labelIcon(lbl)
                    return (
                      <span key={lbl} className="label-badge" title={lbl}>
                        {Icon && <Icon size={12} />}
                        {lbl.length < 12 ? lbl : lbl.slice(0, 10) + '…'}
                      </span>
                    )
                  })}
                  {h.labels.length > 8 && (
                    <span className="label-badge label-more">+{h.labels.length - 8}</span>
                  )}
                </div>
              )}

              {/* Legacy tags fallback */}
              {h.tags?.length > 0 && !hasLabels && (
                <div className="hotel-tags">
                  {h.tags.map((t) => <span key={t} className="tag">{t}</span>)}
                </div>
              )}

              {/* Room types */}
              {hasRooms && (
                <div className="hotel-rooms">
                  <span className="rooms-heading">Available rooms:</span>
                  {h.rooms.slice(0, 3).map((r, i) => (
                    <div key={i} className="room-row">
                      <span className="room-name">{r.name}</span>
                      {r.price_per_night != null && (
                        <span className="room-price">{r.price_per_night} {h.currency}/night</span>
                      )}
                      {r.bed_type && <span className="room-bed">{r.bed_type}</span>}
                      {r.includes && <span className="room-includes">{r.includes}</span>}
                    </div>
                  ))}
                  {h.rooms.length > 3 && (
                    <span className="room-more">+{h.rooms.length - 3} more</span>
                  )}
                </div>
              )}

              <button
                className="select-btn"
                onClick={(e) => { e.stopPropagation(); setSelected(h) }}
              >
                {selected?.id === h.id ? 'Selected' : 'Review'}
              </button>
            </article>
            )
          })}
        </div>
      )}

      {selected && (
        <div className="confirm-box">
          <h3>Continue safely — {selected.name}</h3>
          <p>
            Recheck the room, cancellation policy, final price, taxes, and availability
            on the provider before entering traveler or payment details.
          </p>
          {selected.url ? (
            <a className="confirm-btn" href={selected.url} target="_blank" rel="noopener noreferrer">
              Open provider to verify and book <ExternalLink size={15} />
            </a>
          ) : (
            <p className="source-note">
              <ShieldAlert size={15} /> This source did not provide a booking URL. Search the hotel name on your preferred provider.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
