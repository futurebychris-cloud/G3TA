import { useEffect, useMemo, useRef, useState } from 'react'

import { useAccessibilitySettings } from '../accessibility/AccessibilityContext.jsx'
import ConfirmationDialog from './accessibility/ConfirmationDialog.jsx'
import ReadAloudButton from './accessibility/ReadAloudButton.jsx'

import { hasAmapCredentials, loadAmap, searchAmapSegment } from '../lib/amap.js'
import {
  buildRouteModel,
  formatDistance,
  formatDuration,
  projectPoints,
  routeSegments,
  uniqueMarkerStops,
} from '../utils/routePlan.js'

const AMAP_KEY = import.meta.env.VITE_AMAP_KEY || ''
const AMAP_SECURITY_CODE = import.meta.env.VITE_AMAP_SECURITY_CODE || ''
const AMAP_CONFIGURED = hasAmapCredentials(AMAP_KEY, AMAP_SECURITY_CODE)
const EMPTY_POINTS = []

const LOCAL_ROUTE_MODES = [
  { id: 'walking', label: 'Walking' },
  { id: 'driving', label: 'Driving' },
  { id: 'overview', label: 'Line preview' },
]
const TRANSPORT_ROUTE_MODES = [
  { id: 'amap', label: 'AMap overview' },
  { id: 'overview', label: 'Line preview' },
]

const ROLE_LABEL = {
  departure: 'Departure point',
  arrival: 'Arrival point',
  start: 'Start from hotel',
  visit: 'Activity stop',
  return: 'Return to hotel',
}

function seniorRecommendations(points, agentOutputs) {
  if (!points?.length) return []
  const choices = []
  const add = (point, recommendation) => {
    if (point && !choices.some(({ point: current }) => current === point)) choices.push({ point, recommendation })
  }
  const hotelPoint = points.find(({ type }) => type === 'housing')
  add(hotelPoint || points[0], 'Top Recommendation')

  const activities = agentOutputs?.activity?.recommended || []
  const findActivityPoint = (activity) => points.find((point) => point.label === activity?.name)
  const byValue = [...activities].sort((a, b) => Number(a.price ?? Infinity) - Number(b.price ?? Infinity))
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

function StaticRoutePreview({ route }) {
  const width = 800
  const height = 580
  const projectedPath = projectPoints(route.stops, width, height)
  const projectedMarkers = projectPoints(uniqueMarkerStops(route.stops), width, height)
  const path = projectedPath.map((point) => `${point.x},${point.y}`).join(' ')

  if (!projectedPath.length) {
    return <div className="route-empty">No coordinates are available for this route yet.</div>
  }

  return (
    <svg
      className="route-preview-svg"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`Route preview for ${route.title}`}
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        <pattern id="route-grid" width="48" height="48" patternUnits="userSpaceOnUse">
          <path d="M 48 0 L 0 0 0 48" className="route-grid-line" fill="none" />
        </pattern>
      </defs>
      <rect width="100%" height="100%" className="route-preview-bg" />
      <rect width="100%" height="100%" fill="url(#route-grid)" />
      {projectedPath.length > 1 && <polyline points={path} className="route-preview-line" />}
      {projectedMarkers.map((point, index) => (
        <g key={`${point.label}-${point.lng}-${point.lat}`} transform={`translate(${point.x} ${point.y})`}>
          <circle r="17" className={`route-preview-marker route-preview-marker--${point.type || 'default'}`} />
          <text className="route-preview-number" textAnchor="middle" dominantBaseline="central">
            {point.markerLabel || index + 1}
          </text>
        </g>
      ))}
    </svg>
  )
}

function TransportationSummary({ result, transportation }) {
  const recommended = transportation.recommended || {}
  const summary = transportation.route_summary || {
    origin: result.agent_outputs?.transportation?.route_summary?.origin || 'Origin',
    destination: result.destination,
    departure_airport: recommended.departure_airport,
    arrival_airport: recommended.arrival_airport,
    carrier: recommended.carrier,
    departure_time: recommended.departure_time,
    duration: recommended.duration,
    stops: recommended.stops,
  }
  const currency = result.cost?.currency || 'USD'

  return (
    <section className="transport-card" aria-label="Transportation Agent recommendation">
      <div>
        <span className="transport-eyebrow">Transportation Agent</span>
        <h3>{summary.origin} → {summary.destination}</h3>
        <p>
          {summary.departure_airport || 'Origin airport'} → {summary.arrival_airport || 'Arrival airport'}
        </p>
      </div>
      <div className="transport-facts">
        <span><strong>{summary.carrier || 'Carrier'}</strong></span>
        <span>{summary.duration || 'Duration pending'}</span>
        <span>{summary.stops === 0 ? 'Non-stop' : `${summary.stops ?? '—'} stop(s)`}</span>
        <span>{summary.departure_time || 'Time pending'}</span>
        <span><strong>{currency} {recommended.price?.toLocaleString?.() ?? transportation.cost ?? '—'}</strong></span>
      </div>
      {transportation.coverage?.note && <p className="transport-note">{transportation.coverage.note}</p>}
    </section>
  )
}

export default function MapView({ points = EMPTY_POINTS, result = null, agentOutputs = null }) {
  const { settings } = useAccessibilitySettings()
  const [showAllPlaces, setShowAllPlaces] = useState(false)
  const [showAllScopes, setShowAllScopes] = useState(false)
  const [pendingRouteMode, setPendingRouteMode] = useState(null)
  const isSenior = settings.preset === 'senior'
  const routeInput = useMemo(
    () => ({
      ...(result || {}),
      agent_outputs: result?.agent_outputs || agentOutputs || {},
      map_points: points?.length ? points : (result?.map_points || []),
    }),
    [agentOutputs, points, result],
  )
  const model = useMemo(() => buildRouteModel(routeInput), [routeInput])
  const transportMode = model.transportationRoute.mode
  const scopes = useMemo(() => [
    ...(model.transportationRoute.stops.length >= 2
      ? [{ id: 'transportation', label: transportMode.charAt(0).toUpperCase() + transportMode.slice(1) }]
      : []),
    ...model.days.map((day) => ({ id: day.id, label: `Day ${day.day}` })),
  ], [model, transportMode])
  const visibleScopes = useMemo(
    () => (isSenior && !showAllScopes ? scopes.slice(0, 3) : scopes),
    [isSenior, scopes, showAllScopes],
  )
  const seniorChoices = useMemo(
    () => seniorRecommendations(points, routeInput.agent_outputs),
    [points, routeInput.agent_outputs],
  )
  const placeEntries = isSenior && !showAllPlaces
    ? seniorChoices
    : points.map((point) => ({ point, recommendation: null }))
  const defaultScope = model.days.find((day) => day.stops.length >= 2)?.id
    || (model.transportationRoute.stops.length >= 2 ? 'transportation' : null)
    || model.days.find((day) => day.stops.length)?.id
    || scopes[0]?.id
    || 'transportation'
  const initialCenter = useMemo(() => {
    const firstStop = model.days.flatMap((day) => day.stops)[0] || model.transportationRoute.stops[0]
    return firstStop ? [firstStop.lng, firstStop.lat] : [116.3974, 39.9093]
  }, [model])
  const [scope, setScope] = useState(defaultScope)
  const [routeMode, setRouteMode] = useState('overview')
  const [mapState, setMapState] = useState('preview')
  const [mapMessage, setMapMessage] = useState('')
  const [routeMessage, setRouteMessage] = useState('')
  const [routeMetrics, setRouteMetrics] = useState(null)
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const amapRef = useRef(null)
  const renderTokenRef = useRef(0)

  useEffect(() => {
    if (!scopes.some((item) => item.id === scope)) setScope(defaultScope)
  }, [defaultScope, scope, scopes])

  useEffect(() => {
    if (isSenior && !showAllScopes && !visibleScopes.some((item) => item.id === scope)) {
      setScope(visibleScopes[0]?.id || defaultScope)
    }
  }, [defaultScope, isSenior, scope, showAllScopes, visibleScopes])

  const activeRoute = scope === 'transportation'
    ? model.transportationRoute
    : model.days.find((day) => day.id === scope) || model.days[0] || model.transportationRoute
  const isTransportation = activeRoute.id === 'transportation'
  const routeModes = isTransportation ? TRANSPORT_ROUTE_MODES : LOCAL_ROUTE_MODES

  useEffect(() => {
    if (isTransportation && !['amap', 'overview'].includes(routeMode)) setRouteMode('overview')
    if (!isTransportation && routeMode === 'amap') setRouteMode('overview')
  }, [isTransportation, routeMode])

  useEffect(() => {
    let cancelled = false
    if (!AMAP_CONFIGURED) {
      setRouteMode('overview')
      setMapState('preview')
      setMapMessage('AMap credentials are not configured. Showing the built-in route preview; add them to the ignored root .env.local file to enable the live map.')
      return undefined
    }

    setMapState('loading')
    setMapMessage('Loading AMap JS API 2.0…')
    loadAmap(AMAP_KEY, AMAP_SECURITY_CODE)
      .then((AMap) => {
        if (cancelled || !containerRef.current) return
        amapRef.current = AMap
        const map = new AMap.Map(containerRef.current, {
          viewMode: '2D',
          zoom: 12,
          center: initialCenter,
          showOversea: true,
        })
        map.addControl(new AMap.Scale())
        map.addControl(new AMap.ToolBar({ position: 'RB' }))
        mapRef.current = map
        setMapState('ready')
        setMapMessage(`AMap is ready for ${routeInput.destination || 'this destination'}. Overseas tiles and routes still require the matching AMap permissions.`)
      })
      .catch((error) => {
        if (cancelled) return
        setRouteMode('overview')
        setMapState('preview')
        setMapMessage(`AMap could not load (${error.message}). The built-in route preview remains available.`)
      })

    return () => {
      cancelled = true
      renderTokenRef.current += 1
      mapRef.current?.destroy()
      mapRef.current = null
      amapRef.current = null
    }
  }, [initialCenter, routeInput.destination])

  useEffect(() => {
    const AMap = amapRef.current
    const map = mapRef.current
    if (mapState !== 'ready' || !AMap || !map) return undefined

    const token = renderTokenRef.current + 1
    renderTokenRef.current = token
    let cancelled = false
    setRouteMetrics(null)
    setRouteMessage(isTransportation
      ? routeMode === 'overview'
        ? 'Showing the built-in coordinate-to-coordinate transportation preview.'
        : `${transportMode} endpoints are shown as an AMap overview, not turn-by-turn navigation.`
      : routeMode === 'overview' ? 'Showing a coordinate-to-coordinate line preview.' : `Requesting the AMap ${routeMode} route…`)

    async function drawRoute() {
      map.clearMap()
      const markerStops = uniqueMarkerStops(activeRoute.stops)
      const markers = markerStops.map((stop, index) => {
        const safeType = ['housing', 'activity', 'transport'].includes(stop.type) ? stop.type : 'default'
        return new AMap.Marker({
          position: [stop.lng, stop.lat],
          offset: new AMap.Pixel(-15, -30),
          title: stop.label,
          content: `<span class="amap-route-marker amap-route-marker--${safeType}"><span>${stop.markerLabel || index + 1}</span></span>`,
        })
      })
      map.add(markers)

      const segments = routeSegments(activeRoute.stops)
      const planned = await Promise.all(segments.map(async ({ from, to }) => {
        if (isTransportation || routeMode === 'overview') {
          return { path: [[from.lng, from.lat], [to.lng, to.lat]], distance: 0, duration: 0, fallback: true }
        }
        try {
          return { ...await searchAmapSegment(AMap, routeMode, from, to), fallback: false }
        } catch (error) {
          return {
            path: [[from.lng, from.lat], [to.lng, to.lat]],
            distance: 0,
            duration: 0,
            fallback: true,
            error: error.message,
          }
        }
      }))
      if (cancelled || renderTokenRef.current !== token) return

      const polylines = planned.map((segment) => new AMap.Polyline({
        path: segment.path,
        strokeColor: isTransportation ? '#80caff' : segment.fallback ? '#ffca6b' : '#b9a4ff',
        strokeWeight: isTransportation ? 4 : 6,
        strokeOpacity: 0.9,
        strokeStyle: segment.fallback ? 'dashed' : 'solid',
        showDir: !isTransportation,
        lineJoin: 'round',
      }))
      map.add(polylines)
      if (markers.length || polylines.length) {
        map.setFitView([...markers, ...polylines], false, [64, 48, 64, 48], 17)
      }

      const fallbackCount = planned.filter((segment) => segment.fallback).length
      const distance = planned.reduce((sum, segment) => sum + segment.distance, 0)
      const duration = planned.reduce((sum, segment) => sum + segment.duration, 0)
      setRouteMetrics({ distance, duration, fallbackCount, segments: planned.length })
      if (isTransportation) {
        setRouteMessage(routeMode === 'overview'
          ? 'Line preview drawn from the transportation coordinates.'
          : 'Transportation overview drawn with AMap Marker and Polyline overlays.')
      } else if (routeMode === 'overview') {
        setRouteMessage('Line preview drawn from the itinerary coordinates.')
      } else if (fallbackCount) {
        setRouteMessage(`${fallbackCount} segment(s) had no usable AMap ${routeMode} result, so those segments use line preview.`)
      } else {
        setRouteMessage(`Live AMap ${routeMode} route loaded successfully.`)
      }
    }

    drawRoute().catch((error) => {
      if (cancelled || renderTokenRef.current !== token) return
      setRouteMetrics(null)
      setRouteMode('overview')
      setMapState('preview')
      setMapMessage(`AMap could not draw this route (${error.message}). The built-in route preview remains available.`)
      setRouteMessage('')
    })
    return () => { cancelled = true }
  }, [activeRoute, isTransportation, mapState, routeMode, transportMode])

  const showPreview = mapState !== 'ready' || routeMode === 'overview'
  const formattedDistance = formatDistance(routeMetrics?.distance)
  const formattedDuration = formatDuration(routeMetrics?.duration)

  function chooseRouteMode(mode) {
    if (isSenior && ['walking', 'driving'].includes(mode)) {
      setPendingRouteMode(mode)
      return
    }
    setRouteMode(mode)
  }

  function confirmRouteMode() {
    setRouteMode(pendingRouteMode)
    setPendingRouteMode(null)
  }

  return (
    <div className="places-view route-explorer">
      <div className="panel-heading">
        <div>
          <span className="section-index">LIVE ROUTE</span>
          <h2>Your journey,<br />one route at a time.</h2>
        </div>
        <p>Switch between the transportation overview and each day. AMap powers live routing when the key has the required regional permissions.</p>
      </div>
      <div className="result-heading-actions">
        <ReadAloudButton
          id={`route-summary-${activeRoute.id}`}
          label={`directions for ${activeRoute.title}`}
          text={[activeRoute.title, activeRoute.date, ...activeRoute.stops.flatMap((stop, index) => [`Stop ${index + 1}`, stop.label, ROLE_LABEL[stop.role] || stop.area || stop.type])]}
        />
      </div>

      <TransportationSummary result={routeInput} transportation={model.transportation} />

      {isSenior && placeEntries.length > 0 && (
        <section className="place-index senior-place-choices" aria-labelledby="senior-place-choices-heading">
          <h3 id="senior-place-choices-heading">Places to know first</h3>
          <ol>
            {placeEntries.map(({ point, recommendation }, index) => (
              <li key={`${point.label}-${index}`}>
                <span className="place-number">{String(index + 1).padStart(2, '0')}</span>
                <span>
                  {recommendation && <small className="senior-choice-label">{recommendation}</small>}
                  <strong>{point.label}</strong>
                  <small>{point.type || 'Place'}. {point.area || 'Area pending'}</small>
                </span>
              </li>
            ))}
          </ol>
          {isSenior && points.length > seniorChoices.length && (
            <button className="show-more-results" type="button" aria-expanded={showAllPlaces} onClick={() => setShowAllPlaces((current) => !current)}>
              {showAllPlaces ? 'Show fewer places' : `Show all ${points.length} places`}
            </button>
          )}
        </section>
      )}

      <div className="route-toolbar">
        <div className="route-scope-tabs" role="group" aria-label="Choose route scope">
          {visibleScopes.map((item) => (
            <button
              type="button"
              key={item.id}
              className={scope === item.id ? 'route-control active' : 'route-control'}
              aria-pressed={scope === item.id}
              onClick={() => setScope(item.id)}
            >
              {item.label}
            </button>
          ))}
          {isSenior && scopes.length > 3 && (
            <button className="route-control" type="button" aria-expanded={showAllScopes} onClick={() => setShowAllScopes((current) => !current)}>
              {showAllScopes ? 'Show fewer routes' : 'Show all routes'}
            </button>
          )}
        </div>
        <div className="route-mode-tabs" role="group" aria-label={isTransportation ? 'Choose transportation map mode' : 'Choose local route mode'}>
            {routeModes.map((mode) => (
              <button
                type="button"
                key={mode.id}
                className={routeMode === mode.id ? 'route-control active' : 'route-control'}
                aria-pressed={routeMode === mode.id}
                disabled={mapState !== 'ready' && mode.id !== 'overview'}
                onClick={() => chooseRouteMode(mode.id)}
              >
                {mode.label}
              </button>
            ))}
          </div>
      </div>

      <div className="places-layout route-layout">
        <div className="map-canvas route-stage">
          <div
            ref={containerRef}
            className={showPreview ? 'amap-canvas hidden' : 'amap-canvas'}
            role="region"
            aria-label="AMap route map"
          />
          {showPreview && <StaticRoutePreview route={activeRoute} />}
          {mapState === 'loading' && <div className="route-loading">Loading AMap…</div>}
          <span className={`route-map-state route-map-state--${showPreview ? 'preview' : mapState}`}>
            {showPreview ? 'Route preview' : 'AMap live'}
          </span>
        </div>

        <aside className="place-index route-sidebar" aria-label="Selected route details">
          <div className="route-sidebar-head">
            <span className="section-index">{isTransportation ? `${transportMode} route` : `Day ${activeRoute.day}`}</span>
            <h3>{activeRoute.title}</h3>
            {activeRoute.date && <p>{activeRoute.date}</p>}
          </div>
          {(formattedDistance || formattedDuration) && (
            <div className="route-metrics">
              {formattedDistance && <span>{formattedDistance}</span>}
              {formattedDuration && <span>{formattedDuration}</span>}
            </div>
          )}
          <ol className="route-stops">
            {activeRoute.stops.map((stop, index) => (
              <li key={`${stop.role}-${stop.label}-${index}`}>
                <span className="place-number">{String(index + 1).padStart(2, '0')}</span>
                <span>
                  <strong>{stop.label}</strong>
                  <small>{ROLE_LABEL[stop.role] || stop.area || stop.type}</small>
                </span>
              </li>
            ))}
          </ol>
          {!activeRoute.stops.length && <p className="muted">No mappable stops are available.</p>}
          {!isTransportation && (
            <p className="route-data-note">
              Only itinerary records with valid coordinates are mapped. AI-generated locations and routes require verification.
            </p>
          )}
        </aside>
      </div>

      <div className="route-status" aria-live="polite">
        <p>{mapMessage}</p>
        {routeMessage && <p>{routeMessage}</p>}
      </div>
      <ConfirmationDialog
        open={Boolean(pendingRouteMode)}
        title={`Start ${pendingRouteMode || ''} directions?`}
        description="The map will request a route for the selected stops. Check the route against local signs and official travel information."
        onCancel={() => setPendingRouteMode(null)}
        onConfirm={confirmRouteMode}
      />
    </div>
  )
}
