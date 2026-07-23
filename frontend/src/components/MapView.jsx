import { useCallback, useEffect, useMemo, useState } from 'react'
import { BedDouble, Camera, MapPin, Navigation, PlaneLanding, UtensilsCrossed } from 'lucide-react'
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useAccessibilitySettings } from '../accessibility/AccessibilityContext.jsx'

// Fix default marker icon issue with bundlers
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
})

// ---- Gaode (高德) tile URLs ----
const GAODE_TILES = {
  standard: {
    url: 'https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}',
    attribution: '&copy; <a href="https://www.amap.com/">高德地图</a>',
    subdomains: ['1', '2', '3', '4'],
    label: '高德标准',
  },
  satellite: {
    url: 'https://webst0{s}.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}',
    attribution: '&copy; <a href="https://www.amap.com/">高德地图</a>',
    subdomains: ['1', '2', '3', '4'],
    label: '高德卫星',
  },
  osm: {
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    label: 'OpenStreetMap',
  },
}

// Custom colored markers per type
function createIcon(color, iconType) {
  const svg = iconType === 'housing'
    ? `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline></svg>`
    : iconType === 'transport'
      ? `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><path d="M22 17.5H2M22 17.5L19 9H5L2 17.5M22 17.5a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0zM7 17.5a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0z"/></svg>`
      : iconType === 'restaurant'
        ? `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8h1a4 4 0 0 1 0 8h-1"></path><path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z"></path><line x1="6" y1="1" x2="6" y2="4"></line><line x1="10" y1="1" x2="10" y2="4"></line><line x1="14" y1="1" x2="14" y2="4"></line></svg>`
      : `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>`

  return L.divIcon({
    className: 'custom-map-marker',
    html: `<div style="background:${color};width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 12px rgba(0,0,0,.3);border:2px solid white;">${svg}</div>`,
    iconSize: [36, 36],
    iconAnchor: [18, 18],
    popupAnchor: [0, -20],
  })
}

const TYPE_META = {
  housing: { color: '#ff6b4a', label: 'Stay', icon: BedDouble },
  activity: { color: '#4BC0C0', label: 'Experience', icon: Camera },
  transport: { color: '#80caff', label: 'Transit', icon: PlaneLanding },
  restaurant: { color: '#f5a623', label: 'Dining', icon: UtensilsCrossed },
}

function seniorRecommendations(points, agentOutputs) {
  if (!points?.length) return []
  const choices = []
  const add = (point, recommendation) => {
    if (point && !choices.some(({ point: current }) => current === point)) {
      choices.push({ point, recommendation })
    }
  }
  const hotelPoint = points.find(({ type }) => type === 'housing')
  add(hotelPoint || points[0], 'Top Recommendation')

  const activities = agentOutputs?.activity?.recommended || []
  const findActivityPoint = (activity) => points.find((point) => point.label === activity?.name)
  const byValue = [...activities].sort((a, b) => (
    Number(a.price ?? a.ticket_price ?? Infinity) - Number(b.price ?? b.ticket_price ?? Infinity)
  ))
  add(findActivityPoint(byValue[0]), 'Best Value')

  if (hotelPoint) {
    const closest = points
      .filter(({ type }) => type === 'activity')
      .map((point) => ({ point, distance: Math.hypot(point.lat - hotelPoint.lat, point.lng - hotelPoint.lng) }))
      .sort((a, b) => a.distance - b.distance)
      .find(({ point }) => !choices.some(({ point: current }) => current === point))
    add(closest?.point, 'Closest')
  }
  points.forEach((point) => {
    if (choices.length < 3) add(point, 'Recommended')
  })
  return choices
}

function createRouteUrl(pointA, pointB) {
  const lat1 = pointA.lat, lng1 = pointA.lng
  const lat2 = pointB.lat, lng2 = pointB.lng
  return `https://www.google.com/maps/dir/${lat1},${lng1}/${lat2},${lng2}`
}

// Auto-fit map bounds to show all points
function FitBounds({ points }) {
  const map = useMap()
  useEffect(() => {
    if (points.length === 0) return
    if (points.length === 1) {
      map.setView([points[0].lat, points[0].lng], 14)
      return
    }
    const bounds = L.latLngBounds(points.map(p => [p.lat, p.lng]))
    map.fitBounds(bounds, { padding: [50, 50], maxZoom: 15 })
  }, [map, points])
  return null
}

export default function MapView({ points = [], agentOutputs = null, result = null }) {
  points = points || []
  const { settings } = useAccessibilitySettings()
  const [selectedRoute, setSelectedRoute] = useState(null)
  const [realRoutes, setRealRoutes] = useState({})  // { "0-1": [[lat,lng],...] }
  const [showAllPlaces, setShowAllPlaces] = useState(false)
  const isSenior = settings.preset === 'senior'
  const resolvedAgentOutputs = result?.agent_outputs || agentOutputs || {}
  const seniorChoices = useMemo(
    () => seniorRecommendations(points, resolvedAgentOutputs),
    [points, resolvedAgentOutputs],
  )
  const placeEntries = isSenior && !showAllPlaces
    ? seniorChoices
    : points.map((point) => ({ point, recommendation: null }))

  // Fetch real route path from Gaode API for a segment
  const fetchRoute = useCallback(async (fromIdx, toIdx) => {
    const key = `${fromIdx}-${toIdx}`
    if (realRoutes[key]) return  // already fetched

    const from = points[fromIdx]
    const to = points[toIdx]
    if (!from || !to) return

    try {
      const apiBase = import.meta.env.VITE_API_BASE || 'http://localhost:8000'
      const res = await fetch(`${apiBase}/route/path?` + new URLSearchParams({
        origin_lat: from.lat,
        origin_lng: from.lng,
        dest_lat: to.lat,
        dest_lng: to.lng,
        mode: 'driving',
      }))
      if (res.ok) {
        const data = await res.json()
        if (data.path && data.path.length > 0) {
          setRealRoutes(prev => ({ ...prev, [key]: data.path }))
        }
      }
    } catch (e) {
      console.warn('[MapView] route fetch failed:', e)
    }
  }, [points, realRoutes])

  // Pre-fetch routes between consecutive points
  useEffect(() => {
    if (!points || points.length < 2) return
    // Fetch routes for nearby points (within same city)
    for (let i = 0; i < points.length - 1; i++) {
      const a = points[i]
      const b = points[i + 1]
      // Only fetch if points have the same area (same city routing)
      if (a.area && b.area && a.area === b.area) {
        fetchRoute(i, i + 1)
      }
    }
  }, [points, fetchRoute])

  // Build route segments — use real Gaode paths when available, else straight lines
  const routeSegments = useMemo(() => {
    const segments = []
    for (let i = 0; i < points.length - 1; i++) {
      const key = `${i}-${i + 1}`
      const realPath = realRoutes[key]
      if (realPath && realPath.length >= 2) {
        // Use real road path from Gaode
        segments.push({
          positions: realPath,
          from: points[i],
          to: points[i + 1],
          isReal: true,
        })
      } else {
        // Fallback: straight line
        segments.push({
          positions: [[points[i].lat, points[i].lng], [points[i + 1].lat, points[i + 1].lng]],
          from: points[i],
          to: points[i + 1],
          isReal: false,
        })
      }
    }
    return segments
  }, [points, realRoutes])

  const center = useMemo(() => {
    if (!points.length) return [0, 0]
    const lats = points.map(p => p.lat)
    const lngs = points.map(p => p.lng)
    return [(Math.min(...lats) + Math.max(...lats)) / 2, (Math.min(...lngs) + Math.max(...lngs)) / 2]
  }, [points])

  // Count point types for legend
  const typeCounts = useMemo(() => {
    const counts = {}
    points.forEach(p => { counts[p.type] = (counts[p.type] || 0) + 1 })
    return counts
  }, [points])

  if (!points.length) {
    return (
      <div className="places-view">
        <div className="panel-heading">
          <div><span className="section-index">YOUR PLACES</span><h2>Real maps, real locations.<br />Not an illustration.</h2></div>
          <p>高德地图瓦片 · 所有坐标来自 Agent 实时数据</p>
        </div>
        <div className="empty-state"><MapPin size={28} /><h3>No map points yet</h3><p>Locations will appear here when they are available.</p></div>
      </div>
    )
  }

  const routeColors = ['#ff6b4a', '#4BC0C0', '#80caff', '#f5a623', '#ccf06c', '#b9a4ff', '#ffca6b']

  return (
      <div className="places-view">
        <div className="panel-heading">
          <div>
            <span className="section-index">YOUR PLACES</span>
            <h2>Everything worth finding,<br />on a real map.</h2>
          </div>
          <p>
            高德地图底图 · 所有坐标来自专业 Agent 实时数据
            {Object.keys(realRoutes).length > 0 && ` · ${Object.keys(realRoutes).length} 条真实路线`}
          </p>
        </div>

      <div className="places-layout">
        <div className="leaflet-map-container" style={{ minHeight: 580, borderRadius: 'var(--radius)', overflow: 'hidden' }}>
          <MapContainer
            center={center}
            zoom={13}
            style={{ height: 580, width: '100%' }}
            scrollWheelZoom={true}
            attributionControl={true}
          >
            <TileLayer
              attribution={GAODE_TILES.standard.attribution}
              url={GAODE_TILES.standard.url}
              subdomains={GAODE_TILES.standard.subdomains}
            />

            <FitBounds points={points} />

            {/* Route polylines — real road paths (solid) or straight lines (dashed) */}
            {routeSegments.map((seg, idx) => (
              <Polyline
                key={`route-${idx}`}
                positions={seg.positions}
                pathOptions={{
                  color: routeColors[idx % routeColors.length],
                  weight: seg.isReal ? 4 : 3,
                  opacity: seg.isReal ? 0.85 : 0.7,
                  dashArray: seg.isReal ? undefined : '8 4',
                }}
              />
            ))}

            {/* Markers */}
            {points.map((point, index) => {
              const meta = TYPE_META[point.type] || TYPE_META.activity
              const icon = createIcon(meta.color, point.type)
              return (
                <Marker
                  key={`${point.label}-${index}`}
                  position={[point.lat, point.lng]}
                  icon={icon}
                >
                  <Popup>
                    <div style={{ minWidth: 180 }}>
                      <strong>{point.label}</strong>
                      <br />
                      <small style={{ color: '#666' }}>
                        {meta.label} · {point.area || 'View on map'}
                      </small>
                      {point.star_rating != null && point.type === 'housing' && (
                        <><br /><small style={{ color: '#e6a817' }}>★ {point.star_rating} stars</small></>
                      )}
                      {point.rating != null && point.type === 'restaurant' && (
                        <><br /><small style={{ color: '#e6a817' }}>★ {point.rating} rating</small></>
                      )}
                      {point.ticket_price != null && point.type === 'activity' && (
                        <><br /><small style={{ color: '#2c7a3d' }}>¥{point.ticket_price} ticket</small></>
                      )}
                      {point.price != null && point.type === 'restaurant' && (
                        <><br /><small style={{ color: '#2c7a3d' }}>¥{point.price} avg</small></>
                      )}
                      {point.cuisine && (
                        <><br /><small style={{ color: '#f5a623' }}>{point.cuisine}</small></>
                      )}
                      {point.dish && (
                        <><br /><small style={{ color: '#888' }}>{point.dish}</small></>
                      )}
                      <br />
                      <a
                        href={`https://www.google.com/maps?q=${point.lat},${point.lng}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ fontSize: '0.75rem', color: '#4285F4' }}
                      >
                        Google Maps ↗
                      </a>
                      {' · '}
                      <a
                        href={`https://uri.amap.com/marker?position=${point.lng},${point.lat}&name=${encodeURIComponent(point.label)}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ fontSize: '0.75rem', color: '#4285F4' }}
                      >
                        高德地图 ↗
                      </a>
                    </div>
                  </Popup>
                </Marker>
              )
            })}
          </MapContainer>
        </div>

        <aside className="place-index">
          <span className="section-index">LOCATION INDEX</span>

          {/* Legend */}
          <div style={{ marginBottom: 12, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {Object.entries(TYPE_META).map(([type, meta]) => {
              if (!typeCounts[type]) return null
              const Icon = meta.icon
              return (
                <span key={type} style={{
                  display: 'inline-flex', alignItems: 'center', gap: 4,
                  fontSize: '0.7rem', color: '#555', background: '#f5f5f5',
                  padding: '2px 8px', borderRadius: 12,
                }}>
                  <Icon size={12} color={meta.color} />
                  {meta.label} ({typeCounts[type]})
                </span>
              )
            })}
          </div>

          <ol>
            {placeEntries.map(({ point, recommendation }, index) => {
              const meta = TYPE_META[point.type] || TYPE_META.activity
              const prev = index > 0 ? placeEntries[index - 1]?.point : null
              const fromIndex = prev ? points.indexOf(prev) : -1
              const toIndex = points.indexOf(point)
              const routeKey = fromIndex >= 0 && toIndex === fromIndex + 1
                ? `${fromIndex}-${toIndex}`
                : null
              const hasRealRoute = routeKey && realRoutes[routeKey]
              return (
                <li key={`${point.label}-list`}>
                  <span className="place-number">{String(index + 1).padStart(2, '0')}</span>
                  <span>
                    {recommendation && <span className="senior-choice-label">{recommendation}</span>}
                    <strong>{point.label}</strong>
                    <small>
                      {meta.label}
                      {point.type === 'restaurant' && point.cuisine && ` · ${point.cuisine}`}
                      {point.type === 'restaurant' && point.price && ` · ¥${point.price}`}
                      {' · '}{point.area || 'Area pending'}
                      {hasRealRoute && ' 🛣'}
                    </small>
                    {prev && (
                      <button
                        className="route-hint-btn"
                        onClick={() => setSelectedRoute(selectedRoute === index ? null : index)}
                        title={hasRealRoute ? 'Gaode real road route' : 'Straight-line estimate'}
                      >
                        <Navigation size={11} />
                        {selectedRoute === index ? 'Hide route' : `From ${prev.label}`}
                        {hasRealRoute && <span style={{ fontSize: '0.6rem', opacity: 0.7 }}> (real)</span>}
                      </button>
                    )}
                  </span>
                </li>
              )
            })}
          </ol>
          {isSenior && points.length > 3 && (
            <button
              className="show-more-results"
              type="button"
              aria-expanded={showAllPlaces}
              onClick={() => setShowAllPlaces((current) => !current)}
            >
              {showAllPlaces ? 'Show fewer places' : `Show all ${points.length} places`}
            </button>
          )}
          <div className="map-disclaimer">
            <p>
              {Object.keys(realRoutes).length > 0
                ? `Solid lines = real Gaode driving routes. Dashed lines = straight-line estimates. Click markers for navigation.`
                : `Route lines connect stops in itinerary order. Click markers for navigation links.`}
            </p>
          </div>
        </aside>
      </div>
    </div>
  )
}
