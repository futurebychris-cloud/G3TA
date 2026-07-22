import { useEffect, useMemo, useState } from 'react'
import { BedDouble, Check, LoaderCircle, MapPin, RefreshCw, Search, ShieldAlert, Star, ImageOff, Info, Wallet, Sparkles, Bath, Coffee, Wifi, Tv, Wind, Car, Dumbbell, Waves, UtensilsCrossed } from 'lucide-react'
import { streamBookingSearch, confirmBooking, markBookingPaid } from '../api.js'

const STAGES = [
  { key: 'search', label: 'Search', note: 'Querying the live hotel APIs and Ctrip', icon: Search },
  { key: 'filtering', label: 'Filtering', note: 'Dropping above budget / below rating, ranking', icon: Check },
  { key: 'outputting', label: 'Outputting', note: 'Compiling your shortlist of stays', icon: BedDouble },
  { key: 'confirming', label: 'Confirming', note: 'Driving the booking to the payment step', icon: Wallet },
]

const SOURCE_LABEL = {
  api: 'Real hotel API',
  ctrip: 'Ctrip (携程) live',
  openstreetmap: 'OpenStreetMap (real, price to confirm)',
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
  const [identity, setIdentity] = useState({ name: '', id_number: '', phone: '' })
  const [payment, setPayment] = useState('wechat')
  const [confirming, setConfirming] = useState(false)
  const [confirmResult, setConfirmResult] = useState(null)

  async function runSearch() {
    setError(null)
    setHotels([])
    setSelected(null)
    setConfirmResult(null)
    setSource(null)
    setStages(Object.fromEntries(STAGES.map((s) => [s.key, 'pending'])))
    setSearching(true)
    setStages((s) => ({ ...s, search: 'running' }))
    try {
      const req = {
        location: trip.location,
        check_in: trip.dates.start,
        check_out: trip.dates.end,
        adults: 1,
        children: 0,
        rooms: 1,
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

  // Auto-run the search when the panel opens.
  useEffect(() => {
    runSearch()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function handleConfirm() {
    if (!selected) return
    setConfirming(true)
    setStages((s) => ({ ...s, confirming: 'running' }))
    setConfirmResult(null)
    try {
      const res = await confirmBooking({
        id_number: identity.id_number,
        name: identity.name || undefined,
        phone: identity.phone || undefined,
        hotel: {
          id: selected.id,
          name: selected.name,
          url: selected.url || '',
          room_type: null,
          price_total: selected.price_per_night || null,
          currency: selected.currency || 'CNY',
        },
        check_in: trip.dates.start,
        check_out: trip.dates.end,
        rooms: 1,
        adults: 1,
        children: 0,
        payment_method: payment,
      })
      setConfirmResult(res)
      setStages((s) => ({ ...s, confirming: 'done' }))
    } catch (e) {
      setError(e.message)
      setStages((s) => ({ ...s, confirming: 'pending' }))
    } finally {
      setConfirming(false)
    }
  }

  async function handleMarkPaid() {
    if (!confirmResult?.route) return
    const updated = await markBookingPaid(confirmResult.route.id, confirmResult.route.order_no)
    setConfirmResult((r) => ({ ...r, status: 'confirmed', route: updated }))
  }

  return (
    <div className="booking-panel">
      <div className="panel-heading">
        <div>
          <span className="section-index">BOOK YOUR STAY</span>
          <h2>Real hotels, real booking.<br />No invented data.</h2>
        </div>
        <p>
          Live search across the real hotel APIs, then Ctrip (携程) via Playwright, then
          OpenStreetMap. Pick a stay and we drive the booking to the payment step.
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
          <RefreshCw size={15} className={searching ? 'spin' : ''} /> {searching ? 'Searching…' : 'Search again'}
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
                    href={`https://www.google.com/maps?q=${h.lat},${h.lng}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                  >
                    Google Maps
                  </a>
                  <span>·</span>
                  <a
                    href={`https://uri.amap.com/marker?position=${h.lng},${h.lat}&name=${encodeURIComponent(h.name)}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                  >
                    高德地图
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
                {selected?.id === h.id ? 'Selected' : 'Select'}
              </button>
            </article>
            )
          })}
        </div>
      )}

      {selected && (
        <div className="confirm-box">
          <h3>Confirm booking — {selected.name}</h3>
          <div className="id-grid">
            <label><span>Name</span>
              <input value={identity.name} onChange={(e) => setIdentity({ ...identity, name: e.target.value })} placeholder="Traveler name" />
            </label>
            <label><span>ID number</span>
              <input value={identity.id_number} onChange={(e) => setIdentity({ ...identity, id_number: e.target.value })} placeholder="ID / passport no." />
            </label>
            <label><span>Phone</span>
              <input value={identity.phone} onChange={(e) => setIdentity({ ...identity, phone: e.target.value })} placeholder="Contact phone" />
            </label>
          </div>
          <div className="pay-toggle">
            <button className={payment === 'wechat' ? 'active' : ''} onClick={() => setPayment('wechat')}>微信 WeChat</button>
            <button className={payment === 'alipay' ? 'active' : ''} onClick={() => setPayment('alipay')}>支付宝 Alipay</button>
          </div>
          <button className="confirm-btn" onClick={handleConfirm} disabled={confirming}>
            {confirming ? <><LoaderCircle className="spinner" size={15} /> Confirming…</> : 'Confirm booking'}
          </button>

          {confirmResult && (
            <div className={`confirm-result ${confirmResult.status}`}>
              {confirmResult.status === 'pending_payment' && (
                <>
                  <p className="ok">{confirmResult.message}</p>
                  {confirmResult.order_no && <p>Order no: <strong>{confirmResult.order_no}</strong></p>}
                  <p className="muted">Pay in your own {payment === 'wechat' ? 'WeChat' : 'Alipay'} app, then:</p>
                  <button className="paid-btn" onClick={handleMarkPaid}>标记已支付 (Mark as paid)</button>
                </>
              )}
              {confirmResult.status === 'confirmed' && (
                <p className="ok"><Check size={15} /> Booking confirmed — order {confirmResult.route?.order_no}.</p>
              )}
              {confirmResult.status === 'failed' && (
                <p className="fail">{confirmResult.message}</p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
