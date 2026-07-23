import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { BedDouble, Camera, MapPin, Navigation, PlaneLanding } from 'lucide-react'
import { GoogleMap, Marker, InfoWindow, Polyline, useJsApiLoader } from '@react-google-maps/api'
import { useAccessibilitySettings } from '../accessibility/AccessibilityContext.jsx'
import ReadAloudButton from './accessibility/ReadAloudButton.jsx'

const GOOGLE_MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY || ''
// Stable reference — passing a new array/object each render makes
// @react-google-maps/api warn about "unintentional" script reloads.
const GOOGLE_MAP_LIBRARIES = []

// Gaode (高德) tile source, now rendered as a custom Google Maps ImageMapType
// instead of a Leaflet TileLayer. No key required for these public tiles.
function gaodeTileUrl(coord, zoom) {
  const sub = (((coord.x + coord.y) % 4) + 4) % 4 + 1
  return `https://webrd0${sub}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x=${coord.x}&y=${coord.y}&z=${zoom}`
}

// Gaode only has real map/label coverage inside mainland China — outside this box
// its tiles come back blank or unlabeled, so default to Google's own tiles there.
const CHINA_BOUNDS = { minLat: 17.5, maxLat: 53.6, minLng: 73.0, maxLng: 135.1 }

function isChinaTrip(pts) {
  if (!pts?.length) return false
  const inBounds = pts.filter(({ lat, lng }) => (
    lat >= CHINA_BOUNDS.minLat && lat <= CHINA_BOUNDS.maxLat
    && lng >= CHINA_BOUNDS.minLng && lng <= CHINA_BOUNDS.maxLng
  )).length
  return inBounds / pts.length >= 0.5
}

const TYPE_META = {
  housing: {
    color: '#ff6b4a',
    label: 'Stay',
    icon: BedDouble,
    path: '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path><polyline points="9 22 9 12 15 12 15 22"></polyline>',
  },
  transport: {
    color: '#80caff',
    label: 'Transit',
    icon: PlaneLanding,
    path: '<path d="M22 17.5H2M22 17.5L19 9H5L2 17.5M22 17.5a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0zM7 17.5a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0z"/>',
  },
  activity: {
    color: '#4BC0C0',
    label: 'Experience',
    icon: Camera,
    path: '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline>',
  },
}

// Custom colored pin icons per type, built the same way the old Leaflet
// divIcon markers were, just encoded as a data URI for google.maps.Icon.
function markerIcon(type) {
  const meta = TYPE_META[type] || TYPE_META.activity
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="36" height="36" viewBox="0 0 36 36">` +
    `<circle cx="18" cy="18" r="16" fill="${meta.color}" stroke="white" stroke-width="2"/>` +
    `<g transform="translate(6,6)" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${meta.path}</g>` +
    `</svg>`
  return {
    url: `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`,
    scaledSize: new window.google.maps.Size(36, 36),
    anchor: new window.google.maps.Point(18, 18),
  }
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

export default function MapView({ points = [], agentOutputs = null, result = null }) {
  points = points || []
  const { settings } = useAccessibilitySettings()
  const { isLoaded, loadError } = useJsApiLoader({
    id: 'g3ta-google-maps-script',
    googleMapsApiKey: GOOGLE_MAPS_API_KEY,
    libraries: GOOGLE_MAP_LIBRARIES,
  })
  const mapRef = useRef(null)
  const prevPointsRef = useRef(null)
  const [activePoint, setActivePoint] = useState(null)
  const [mapType, setMapType] = useState(() => (isChinaTrip(points) ? 'gaode' : 'roadmap'))
  const [selectedRoute, setSelectedRoute] = useState(null)
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

  // Build route polylines between consecutive points
  const routeSegments = useMemo(() => {
    const segments = []
    for (let i = 0; i < points.length - 1; i++) {
      segments.push({
        path: [
          { lat: points[i].lat, lng: points[i].lng },
          { lat: points[i + 1].lat, lng: points[i + 1].lng },
        ],
        from: points[i],
        to: points[i + 1],
      })
    }
    return segments
  }, [points])

  const center = useMemo(() => {
    if (!points.length) return { lat: 0, lng: 0 }
    const lats = points.map((p) => p.lat)
    const lngs = points.map((p) => p.lng)
    return { lat: (Math.min(...lats) + Math.max(...lats)) / 2, lng: (Math.min(...lngs) + Math.max(...lngs)) / 2 }
  }, [points])

  const registerGaodeLayer = useCallback((map) => {
    const gaode = new window.google.maps.ImageMapType({
      getTileUrl: gaodeTileUrl,
      tileSize: new window.google.maps.Size(256, 256),
      maxZoom: 18,
      minZoom: 3,
      name: 'Gaode',
    })
    map.mapTypes.set('gaode', gaode)
  }, [])

  const handleMapLoad = useCallback((map) => {
    mapRef.current = map
    registerGaodeLayer(map)
    // Gaode tiles are blank/unlabeled outside China — pick the right basemap up front
    // instead of always starting on Gaode and letting non-China trips look broken.
    const initialType = isChinaTrip(points) ? 'gaode' : 'roadmap'
    map.setMapTypeId(initialType)
    setMapType(initialType)
    prevPointsRef.current = points
  }, [registerGaodeLayer, points])

  // Auto-fit map bounds to show all points, same behavior as the old Leaflet FitBounds helper.
  // Also re-picks the basemap (Gaode vs Google) when a new trip's points replace the old ones.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !isLoaded || points.length === 0) return

    if (prevPointsRef.current !== points) {
      prevPointsRef.current = points
      const autoType = isChinaTrip(points) ? 'gaode' : 'roadmap'
      map.setMapTypeId(autoType)
      setMapType(autoType)
    }

    if (points.length === 1) {
      map.setCenter({ lat: points[0].lat, lng: points[0].lng })
      map.setZoom(14)
      return
    }
    const bounds = new window.google.maps.LatLngBounds()
    points.forEach((p) => bounds.extend({ lat: p.lat, lng: p.lng }))
    map.fitBounds(bounds, 50)
  }, [points, isLoaded])

  const toggleMapType = useCallback(() => {
    const map = mapRef.current
    if (!map) return
    setMapType((current) => {
      const next = current === 'gaode' ? 'roadmap' : 'gaode'
      map.setMapTypeId(next)
      return next
    })
  }, [])

  if (!points.length) {
    return (
      <div className="places-view">
        <div className="panel-heading">
          <div><span className="section-index">YOUR PLACES</span><h2>Real maps, real locations.<br />Not an illustration.</h2></div>
          <p>所有坐标来自 Agent 实时数据</p>
        </div>
        <div className="empty-state"><MapPin size={28} /><h3>No map points yet</h3><p>Locations will appear here when they are available.</p></div>
      </div>
    )
  }

  const routeColors = ['#ff6b4a', '#4BC0C0', '#80caff', '#ccf06c', '#b9a4ff', '#ffca6b']
  const activePlace = activePoint != null ? points[activePoint] : null
  const activeMeta = activePlace ? (TYPE_META[activePlace.type] || TYPE_META.activity) : null

  return (
      <div className="places-view">
        <div className="panel-heading">
          <div>
            <span className="section-index">YOUR PLACES</span>
            <h2>Everything worth finding,<br />on a real map.</h2>
          </div>
          <p>{mapType === 'gaode' ? '高德地图底图' : 'Google Maps 底图'} · 所有坐标来自专业 Agent 实时数据。点间虚线为行程路线。</p>
        </div>

      <div className="places-layout">
        <div className="gmap-container" style={{ minHeight: 580, borderRadius: 'var(--radius)', overflow: 'hidden', position: 'relative' }}>
          {!GOOGLE_MAPS_API_KEY && (
            <div className="empty-state">
              <MapPin size={28} />
              <h3>Google Maps key missing</h3>
              <p>Set <code>VITE_GOOGLE_MAPS_API_KEY</code> in <code>.env</code> to display the map.</p>
            </div>
          )}
          {GOOGLE_MAPS_API_KEY && loadError && (
            <div className="empty-state">
              <MapPin size={28} />
              <h3>Map failed to load</h3>
              <p>{String(loadError.message || loadError)}</p>
            </div>
          )}
          {GOOGLE_MAPS_API_KEY && isLoaded && (
            <>
              <button type="button" className="map-type-toggle" onClick={toggleMapType}>
                {mapType === 'gaode' ? 'Switch to Google tiles' : 'Switch to Gaode tiles'}
              </button>
              <GoogleMap
                mapContainerStyle={{ height: 580, width: '100%' }}
                center={center}
                zoom={13}
                onLoad={handleMapLoad}
                options={{
                  mapTypeControl: false,
                  streetViewControl: false,
                  fullscreenControl: true,
                  gestureHandling: 'greedy',
                }}
              >
                {/* Route polylines */}
                {routeSegments.map((seg, idx) => (
                  <Polyline
                    key={`route-${idx}`}
                    path={seg.path}
                    options={{
                      strokeOpacity: 0,
                      strokeWeight: 3,
                      icons: [{
                        icon: { path: 'M 0,-1 0,1', strokeOpacity: 0.7, strokeColor: routeColors[idx % routeColors.length], scale: 3 },
                        offset: '0',
                        repeat: '12px',
                      }],
                    }}
                  />
                ))}

                {/* Markers */}
                {points.map((point, index) => (
                  <Marker
                    key={`${point.label}-${index}`}
                    position={{ lat: point.lat, lng: point.lng }}
                    icon={markerIcon(point.type)}
                    onClick={() => setActivePoint(index)}
                  />
                ))}

                {activePlace && (
                  <InfoWindow
                    position={{ lat: activePlace.lat, lng: activePlace.lng }}
                    onCloseClick={() => setActivePoint(null)}
                  >
                    <div style={{ minWidth: 160 }}>
                      <strong>{activePlace.label}</strong>
                      <br />
                      <small style={{ color: '#666' }}>
                        {activeMeta.label} · {activePlace.area || 'View on map'}
                      </small>
                      {activePlace.star_rating != null && (
                        <><br /><small style={{ color: '#e6a817' }}>★ {activePlace.star_rating} stars</small></>
                      )}
                      {activePlace.ticket_price != null && (
                        <><br /><small style={{ color: '#2c7a3d' }}>¥{activePlace.ticket_price} ticket</small></>
                      )}
                      <br />
                      <a
                        href={`https://www.google.com/maps?q=${activePlace.lat},${activePlace.lng}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ fontSize: '0.75rem', color: '#4285F4' }}
                      >
                        Google Maps ↗
                      </a>
                      {' · '}
                      <a
                        href={`https://uri.amap.com/marker?position=${activePlace.lng},${activePlace.lat}&name=${encodeURIComponent(activePlace.label)}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ fontSize: '0.75rem', color: '#4285F4' }}
                      >
                        高德地图 ↗
                      </a>
                    </div>
                  </InfoWindow>
                )}
              </GoogleMap>
            </>
          )}
        </div>

        <aside className="place-index">
          <div className="place-index-head">
            <span className="section-index">LOCATION INDEX</span>
            <ReadAloudButton
              id="location-index"
              label="the location index"
              text={placeEntries.map(({ point, recommendation }) => (
                `${recommendation ? `${recommendation}: ` : ''}${point.label}, ${(TYPE_META[point.type] || TYPE_META.activity).label}${point.area ? ` in ${point.area}` : ''}.`
              ))}
            />
          </div>
          <ol>
            {placeEntries.map(({ point, recommendation }, index) => {
              const meta = TYPE_META[point.type] || TYPE_META.activity
              const prev = index > 0 ? placeEntries[index - 1]?.point : null
              return (
                <li key={`${point.label}-list`}>
                  <span className="place-number">{String(index + 1).padStart(2, '0')}</span>
                  <span>
                    {recommendation && <span className="senior-choice-label">{recommendation}</span>}
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
            <p>Route lines connect stops in itinerary order. Click markers for navigation links.</p>
          </div>
        </aside>
      </div>
    </div>
  )
}
