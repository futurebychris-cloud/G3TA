import { useEffect, useMemo, useRef, useState } from 'react'
import { BedDouble, Camera, MapPin, Navigation, PlaneLanding } from 'lucide-react'
import { MapContainer, TileLayer, Marker, Popup, Polyline, useMap } from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

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

export default function MapView({ points }) {
  const [selectedRoute, setSelectedRoute] = useState(null)

  if (!points || points.length === 0) {
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

  // Build route polylines between consecutive points
  const routeSegments = useMemo(() => {
    const segments = []
    for (let i = 0; i < points.length - 1; i++) {
      segments.push({
        positions: [[points[i].lat, points[i].lng], [points[i + 1].lat, points[i + 1].lng]],
        from: points[i],
        to: points[i + 1],
      })
    }
    return segments
  }, [points])

  const center = useMemo(() => {
    const lats = points.map(p => p.lat)
    const lngs = points.map(p => p.lng)
    return [(Math.min(...lats) + Math.max(...lats)) / 2, (Math.min(...lngs) + Math.max(...lngs)) / 2]
  }, [points])

  const routeColors = ['#ff6b4a', '#4BC0C0', '#80caff', '#ccf06c', '#b9a4ff', '#ffca6b']

  return (
      <div className="places-view">
        <div className="panel-heading">
          <div>
            <span className="section-index">YOUR PLACES</span>
            <h2>Everything worth finding,<br />on a real map.</h2>
          </div>
          <p>高德地图底图 · 所有坐标来自专业 Agent 实时数据。点间虚线为行程路线。</p>
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

            {/* Route polylines */}
            {routeSegments.map((seg, idx) => (
              <Polyline
                key={`route-${idx}`}
                positions={seg.positions}
                pathOptions={{
                  color: routeColors[idx % routeColors.length],
                  weight: 3,
                  opacity: 0.7,
                  dashArray: '8 4',
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
                    <div style={{ minWidth: 160 }}>
                      <strong>{point.label}</strong>
                      <br />
                      <small style={{ color: '#666' }}>
                        {meta.label} · {point.area || 'View on map'}
                      </small>
                      {point.star_rating != null && (
                        <><br /><small style={{ color: '#e6a817' }}>★ {point.star_rating} stars</small></>
                      )}
                      {point.ticket_price != null && (
                        <><br /><small style={{ color: '#2c7a3d' }}>¥{point.ticket_price} ticket</small></>
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
          <ol>
            {points.map((point, index) => {
              const meta = TYPE_META[point.type] || TYPE_META.activity
              const prev = index > 0 ? points[index - 1] : null
              return (
                <li key={`${point.label}-list`}>
                  <span className="place-number">{String(index + 1).padStart(2, '0')}</span>
                  <span>
                    <strong>{point.label}</strong>
                    <small>{meta.label} · {point.area || 'Area pending'}</small>
                    {prev && (
                      <button
                        className="route-hint-btn"
                        onClick={() => setSelectedRoute(selectedRoute === index ? null : index)}
                        title="Show route"
                      >
                        <Navigation size={11} />
                        {selectedRoute === index ? 'Hide route' : `From ${prev.label}`}
                      </button>
                    )}
                  </span>
                </li>
              )
            })}
          </ol>
          <div className="map-disclaimer">
            <p>Route lines connect stops in itinerary order. Click markers for navigation links.</p>
          </div>
        </aside>
      </div>
    </div>
  )
}
