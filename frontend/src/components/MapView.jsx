import { useEffect, useMemo, useRef, useState } from 'react'
import { MapPin, Navigation, RotateCcw } from 'lucide-react'
import { animate } from 'motion'
import { useAccessibilitySettings } from '../accessibility/AccessibilityContext.jsx'
import ReadAloudButton from './accessibility/ReadAloudButton.jsx'

import { hasAmapCredentials, loadAmap, searchAmapSegment } from '../lib/amap.js'
import {
  buildRouteModel,
  formatDistance,
  formatDuration,
  revealRoutePaths,
  routeSegments,
  uniqueMarkerStops,
} from '../utils/routePlan.js'

// Public browser-demo credentials keep a fresh clone usable without a local
// environment file. Production deployments should override both values through
// VITE_AMAP_* and restrict the demo key by domain and quota in the AMap console.
const AMAP_DEMO_KEY = '0aca2891dd9c7a1123047be9ece54bfb'
const AMAP_DEMO_SECURITY_CODE = 'ecae3007884963fb215c7b03b1fad1d7'
const AMAP_KEY = import.meta.env.VITE_AMAP_KEY || AMAP_DEMO_KEY
const AMAP_SECURITY_CODE = import.meta.env.VITE_AMAP_SECURITY_CODE || AMAP_DEMO_SECURITY_CODE
const AMAP_CONFIGURED = hasAmapCredentials(AMAP_KEY, AMAP_SECURITY_CODE)
const EMPTY_POINTS = []

const LOCAL_ROUTE_MODES = [
  { id: 'walking', label: 'Walking' },
  { id: 'driving', label: 'Driving' },
]
const TRANSPORT_ROUTE_MODES = [
  { id: 'amap', label: 'AMap overview' },
]

const ROLE_LABEL = {
  departure: 'Departure point',
  arrival: 'Arrival point',
  transfer: 'Transfer point',
  start: 'Start from hotel',
  visit: 'Activity stop',
  return: 'Return to hotel',
}

const TYPE_LABEL = {
  housing: 'Stay',
  activity: 'Experience',
  transport: 'Transit',
  restaurant: 'Dining',
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

function TransportationSummary({ result, transportation }) {
  const recommended = transportation.recommended || {}
  const summary = transportation.route_summary || {
    origin: recommended.from || result.agent_outputs?.transportation?.route_summary?.origin || 'Origin',
    destination: recommended.to || result.destination,
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

function amapPlaceUrl(point) {
  return `https://uri.amap.com/marker?position=${point.lng},${point.lat}&name=${encodeURIComponent(point.label)}&src=G3TA&callnative=0`
}

function amapRouteUrl(from, to, routeMode) {
  const mode = routeMode === 'walking' ? 'walk' : 'car'
  return `https://uri.amap.com/navigation?from=${from.lng},${from.lat},${encodeURIComponent(from.label)}&to=${to.lng},${to.lat},${encodeURIComponent(to.label)}&mode=${mode}&policy=1&src=G3TA&callnative=0`
}

function routeModeForScope(scope) {
  return scope === 'transportation' ? 'amap' : 'walking'
}

function formatCost(cost) {
  if (!cost || Number.isNaN(cost)) return ''
  return `¥${Math.round(cost)} est. cost`
}

function useSystemReducedMotion() {
  const [reducedMotion, setReducedMotion] = useState(() => (
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches || false
  ))

  useEffect(() => {
    const mediaQuery = window.matchMedia?.('(prefers-reduced-motion: reduce)')
    if (!mediaQuery) return undefined
    const updatePreference = (event) => setReducedMotion(event.matches)
    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', updatePreference)
    } else {
      mediaQuery.addListener?.(updatePreference)
    }
    return () => {
      if (typeof mediaQuery.removeEventListener === 'function') {
        mediaQuery.removeEventListener('change', updatePreference)
      } else {
        mediaQuery.removeListener?.(updatePreference)
      }
    }
  }, [])

  return reducedMotion
}

export default function MapView({ points = EMPTY_POINTS, result = null, agentOutputs = null }) {
  const { settings } = useAccessibilitySettings()
  const systemReducedMotion = useSystemReducedMotion()
  const shouldReduceMotion = settings.reducedMotion || systemReducedMotion
  const [showAll, setShowAll] = useState(false)
  const isSenior = settings.preset === 'senior'
  const routeInput = useMemo(
    () => ({ ...(result || {}), map_points: points?.length ? points : (result?.map_points || []) }),
    [points, result],
  )
  const model = useMemo(() => buildRouteModel(routeInput), [routeInput])
  const localPoints = routeInput.map_points || EMPTY_POINTS
  const effectiveAgentOutputs = agentOutputs || routeInput.agent_outputs || {}
  const seniorChoices = useMemo(
    () => seniorRecommendations(localPoints, effectiveAgentOutputs),
    [effectiveAgentOutputs, localPoints],
  )
  const listEntries = isSenior && !showAll
    ? seniorChoices
    : localPoints.map((point) => ({ point, recommendation: null }))
  const transportMode = model.transportationRoute.mode
  const scopes = useMemo(() => [
    ...(model.fullTripRoute.stops.length >= 2
      ? [{ id: 'full-trip', label: 'Full trip' }]
      : []),
    ...(model.transportationRoute.stops.length >= 2
      ? [{ id: 'transportation', label: transportMode.charAt(0).toUpperCase() + transportMode.slice(1) }]
      : []),
    ...model.days.map((day) => ({ id: day.id, label: `Day ${day.day}` })),
  ], [model, transportMode])
  const defaultScope = (model.fullTripRoute.stops.length >= 2 ? 'full-trip' : null)
    || model.days.find((day) => day.stops.length >= 2)?.id
    || (model.transportationRoute.stops.length >= 2 ? 'transportation' : null)
    || model.days.find((day) => day.stops.length)?.id
    || scopes[0]?.id
    || 'transportation'
  const initialCenter = useMemo(() => {
    const firstStop = model.fullTripRoute.stops[0]
      || model.days.flatMap((day) => day.stops)[0]
      || model.transportationRoute.stops[0]
    return firstStop ? [firstStop.lng, firstStop.lat] : [116.3974, 39.9093]
  }, [model])
  const [scope, setScope] = useState(defaultScope)
  const [routeMode, setRouteMode] = useState(() => routeModeForScope(defaultScope))
  const [mapState, setMapState] = useState(AMAP_CONFIGURED ? 'loading' : 'error')
  const [mapMessage, setMapMessage] = useState('')
  const [routeMessage, setRouteMessage] = useState('')
  const [routeMetrics, setRouteMetrics] = useState(null)
  const [routeSegmentDetails, setRouteSegmentDetails] = useState([])
  const [routeAnimationProgress, setRouteAnimationProgress] = useState(null)
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const amapRef = useRef(null)
  const renderTokenRef = useRef(0)
  const routeAnimationRef = useRef(null)
  const routePlaybackRef = useRef(null)

  useEffect(() => {
    if (!scopes.some((item) => item.id === scope)) {
      setScope(defaultScope)
      setRouteMode(routeModeForScope(defaultScope))
    }
  }, [defaultScope, scope, scopes])

  const activeRoute = scope === 'transportation'
    ? model.transportationRoute
    : scope === 'full-trip'
      ? model.fullTripRoute
      : model.days.find((day) => day.id === scope)
        || (model.fullTripRoute.stops.length ? model.fullTripRoute : null)
        || model.days[0]
        || model.transportationRoute
  const isTransportation = activeRoute.id === 'transportation'
  const isFullTrip = activeRoute.id === 'full-trip'
  const isDrivingTransportation = isTransportation && /car|driv/.test(transportMode)
  const routeModes = isTransportation ? TRANSPORT_ROUTE_MODES : LOCAL_ROUTE_MODES

  useEffect(() => {
    const validModes = isTransportation ? ['amap'] : ['walking', 'driving']
    if (!validModes.includes(routeMode)) setRouteMode(isTransportation ? 'amap' : 'walking')
  }, [isTransportation, routeMode])

  useEffect(() => {
    let cancelled = false
    if (!AMAP_CONFIGURED) {
      setMapState('error')
      setMapMessage('AMap credentials are not configured. Add the Web JS key and security code to the ignored root .env.local file, then restart the frontend.')
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
        setMapState('error')
        setMapMessage(`AMap could not load (${error.message}).`)
      })

    return () => {
      cancelled = true
      renderTokenRef.current += 1
      routeAnimationRef.current?.stop()
      routeAnimationRef.current = null
      routePlaybackRef.current = null
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
    routeAnimationRef.current?.stop()
    routeAnimationRef.current = null
    routePlaybackRef.current = null
    setRouteAnimationProgress(null)
    setRouteMetrics(null)
    setRouteMessage(isTransportation
      ? isDrivingTransportation
        ? 'Requesting the live AMap driving route between the transportation endpoints…'
        : `${transportMode} endpoints use an animated geographic overview, not a provider-confirmed track.`
      : `Requesting the AMap ${routeMode} route…`)

    async function drawRoute() {
      map.clearMap()
      const markerStops = uniqueMarkerStops(activeRoute.stops)
      const markers = markerStops.map((stop, index) => {
        const safeType = ['housing', 'activity', 'transport', 'restaurant'].includes(stop.type) ? stop.type : 'default'
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
        if (isTransportation && !isDrivingTransportation) {
          return { path: [[from.lng, from.lat], [to.lng, to.lat]], distance: 0, duration: 0, cost: 0, failed: false }
        }
        try {
          const requestedMode = isDrivingTransportation ? 'driving' : routeMode
          const seg = { ...await searchAmapSegment(AMap, requestedMode, from, to), failed: false }
          // Honest cost estimate: taxi-style rate for driving, free for walking.
          seg.cost = requestedMode === 'driving' ? (seg.distance / 1000) * 2.4 : 0
          return seg
        } catch (error) {
          return {
            path: [],
            distance: 0,
            duration: 0,
            cost: 0,
            failed: true,
            error: error.message,
          }
        }
      }))
      if (cancelled || renderTokenRef.current !== token) return

      const drawableSegments = planned.filter((segment) => segment.path.length >= 2)
      const drawablePaths = drawableSegments.map((segment) => segment.path)
      const polylines = drawableSegments.map((segment) => new AMap.Polyline({
          path: segment.path,
          strokeColor: isTransportation ? '#80caff' : routeMode === 'driving' ? '#ff6847' : '#b9a4ff',
          strokeWeight: isTransportation ? 4 : 6,
          strokeOpacity: 0.9,
          strokeStyle: 'solid',
          showDir: !isTransportation && shouldReduceMotion,
          lineJoin: 'round',
        }))
      map.add(polylines)
      if (markers.length || polylines.length) {
        map.setFitView([...markers, ...polylines], false, [64, 48, 64, 48], 17)
      }

      if (drawablePaths.length) {
        const traveler = shouldReduceMotion
          ? null
          : new AMap.Marker({
            position: drawablePaths[0][0],
            offset: new AMap.Pixel(-10, -10),
            zIndex: 300,
            title: `Route progress from ${activeRoute.stops[0]?.label || 'start'} to ${activeRoute.stops.at(-1)?.label || 'destination'}`,
            content: `<span class="amap-route-traveler amap-route-traveler--${routeMode}" aria-hidden="true"></span>`,
          })
        if (traveler) map.add(traveler)

        const playRouteAnimation = () => {
          if (cancelled || renderTokenRef.current !== token || mapRef.current !== map) return
          routeAnimationRef.current?.stop()
          let lastRenderedPercent = -1
          let lastAnnouncedPercent = -5
          polylines.forEach((polyline) => polyline.setOptions?.({ showDir: false }))

          const showRouteProgress = (progress) => {
            if (cancelled || renderTokenRef.current !== token || mapRef.current !== map) return
            const percent = Math.round(progress * 100)
            if (percent === lastRenderedPercent) return
            lastRenderedPercent = percent
            const visiblePaths = revealRoutePaths(drawablePaths, progress)
            visiblePaths.forEach((path, index) => {
              if (!path.length) {
                polylines[index].hide?.()
                return
              }
              polylines[index].show?.()
              polylines[index].setPath(path.length === 1 ? [path[0], path[0]] : path)
            })
            const visibleHead = [...visiblePaths]
              .reverse()
              .find((path) => path.length)
              ?.at(-1)
            if (traveler && visibleHead) traveler.setPosition(visibleHead)
            if (percent >= lastAnnouncedPercent + 5 || percent === 100) {
              lastAnnouncedPercent = percent
              setRouteAnimationProgress(percent)
            }
          }

          showRouteProgress(0)
          const animationDuration = Math.min(24, 16 + drawablePaths.length * 1.25)
          routeAnimationRef.current = animate(0, 1, {
            duration: animationDuration,
            ease: 'easeInOut',
            onUpdate: showRouteProgress,
            onComplete: () => {
              if (cancelled || renderTokenRef.current !== token) return
              showRouteProgress(1)
              polylines.forEach((polyline) => polyline.setOptions?.({ showDir: true }))
              routeAnimationRef.current = null
            },
          })
        }

        if (shouldReduceMotion) {
          polylines.forEach((polyline, index) => {
            polyline.show?.()
            polyline.setPath(drawablePaths[index])
          })
          setRouteAnimationProgress(100)
        } else {
          routePlaybackRef.current = { token, play: playRouteAnimation }
          playRouteAnimation()
        }
      }

      const failedCount = planned.filter((segment) => segment.failed).length
      const distance = planned.reduce((sum, segment) => sum + segment.distance, 0)
      const duration = planned.reduce((sum, segment) => sum + segment.duration, 0)
      const cost = planned.reduce((sum, segment) => sum + (segment.cost || 0), 0)
      setRouteMetrics({ distance, duration, cost, failedCount, segments: planned.length })
      setRouteSegmentDetails(planned)
      if (isTransportation) {
        setRouteMessage(isDrivingTransportation
          ? 'Live AMap driving route loaded between the transportation endpoints.'
          : `${transportMode} overview drawn from provider endpoints. The line is geographic context, not the exact carrier track.`)
      } else if (!planned.length) {
        setRouteMessage('This selection has only one mappable stop, so there is no route segment to calculate.')
      } else if (failedCount) {
        setRouteMessage(`${planned.length - failedCount} route segment(s) loaded; ${failedCount} AMap ${routeMode} segment(s) are unavailable.`)
      } else {
        setRouteMessage(`Live AMap ${routeMode} route loaded successfully.`)
      }
    }

    drawRoute().catch((error) => {
      if (cancelled || renderTokenRef.current !== token) return
      setRouteMetrics(null)
      setMapMessage(`AMap loaded, but this route could not be drawn (${error.message}).`)
      setRouteMessage('Choose another route or routing mode to retry.')
    })
    return () => {
      cancelled = true
      routeAnimationRef.current?.stop()
      routeAnimationRef.current = null
      routePlaybackRef.current = null
    }
  }, [
    activeRoute,
    isDrivingTransportation,
    isTransportation,
    mapState,
    routeMode,
    shouldReduceMotion,
    transportMode,
  ])

  const formattedDistance = formatDistance(routeMetrics?.distance)
  const formattedDuration = formatDuration(routeMetrics?.duration)
  const formattedCost = formatCost(routeMetrics?.cost)
  const mapStateLabel = mapState === 'ready'
    ? 'AMap live'
    : mapState === 'loading'
      ? 'Loading AMap…'
      : 'AMap unavailable'
  const routeAnimationLabel = routeAnimationProgress >= 100
    ? 'Route traced'
    : `Tracing route · ${routeAnimationProgress ?? 0}%`

  return (
    <div className="places-view route-explorer">
      <div className="panel-heading">
        <div>
          <span className="section-index">LIVE ROUTE</span>
          <h2>Your journey,<br />one route at a time.</h2>
        </div>
        <p>Start with the full trip route, then switch to transportation or a single day. Walking and Driving use separate live AMap route plans.</p>
      </div>
      <div className="result-heading-actions">
        <ReadAloudButton
          id="places-summary"
          label="recommended places"
          text={listEntries.flatMap(({ point, recommendation }, index) => [
            recommendation || `Place ${index + 1}`,
            point.label,
            TYPE_LABEL[point.type] || point.type,
            point.area,
          ])}
        />
      </div>

      {isSenior && listEntries.length > 0 && (
        <section className="senior-place-picks place-index" aria-labelledby="senior-place-picks-heading">
          <h3 id="senior-place-picks-heading">Recommended places</h3>
          <ol>
            {listEntries.map(({ point, recommendation }, index) => (
              <li key={`${point.label}-senior-${index}`}>
                <span className="place-number">{String(index + 1).padStart(2, '0')}</span>
                <span>
                  {recommendation && <small className="senior-choice-label">{recommendation}</small>}
                  <strong>{point.label}</strong>
                  <small>{TYPE_LABEL[point.type] || point.type}. {point.area || 'Area pending'}</small>
                  {point.cuisine && <small>{point.cuisine}</small>}
                  {point.rating != null && <small>★ {point.rating} rating</small>}
                  {point.price != null && <small>¥{point.price} avg</small>}
                  {point.dish && <small>{point.dish}</small>}
                </span>
              </li>
            ))}
          </ol>
          {localPoints.length > seniorChoices.length && (
            <button
              className="show-more-results"
              type="button"
              aria-expanded={showAll}
              onClick={() => setShowAll((current) => !current)}
            >
              {showAll ? 'Show fewer places' : `Show all ${localPoints.length} places`}
            </button>
          )}
        </section>
      )}

      <TransportationSummary result={routeInput} transportation={model.transportation} />

      <div className="route-toolbar">
        <div className="route-scope-tabs" aria-label="Choose route scope">
          {scopes.map((item) => (
            <button
              type="button"
              key={item.id}
              className={scope === item.id ? 'route-control active' : 'route-control'}
              aria-pressed={scope === item.id}
              onClick={() => {
                setScope(item.id)
                setRouteMode(routeModeForScope(item.id))
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div className="route-mode-tabs" aria-label={isTransportation ? 'Choose transportation map mode' : 'Choose local route mode'}>
          {routeModes.map((mode) => (
            <button
              type="button"
              key={mode.id}
              className={routeMode === mode.id ? 'route-control active' : 'route-control'}
              aria-pressed={routeMode === mode.id}
              disabled={mapState !== 'ready'}
              onClick={() => setRouteMode(mode.id)}
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
            className={mapState === 'ready' ? 'amap-canvas' : 'amap-canvas hidden'}
            role="region"
            aria-label="AMap route map"
          />
          {mapState === 'loading' && <div className="route-loading">Loading AMap…</div>}
          {mapState === 'error' && (
            <div className="route-unavailable">
              <MapPin size={28} />
              <h3>AMap unavailable</h3>
              <p>{mapMessage || 'The live route map could not be loaded.'}</p>
            </div>
          )}
          <span className={`route-map-state route-map-state--${mapState}`}>
            {mapStateLabel}
          </span>
          {!isTransportation && routeAnimationProgress != null && (
            <div className="route-animation-control">
              <span aria-live="polite">
                <span className={routeAnimationProgress < 100 ? 'route-animation-dot active' : 'route-animation-dot'} />
                {routeAnimationLabel}
              </span>
              {!shouldReduceMotion && (
                <button
                  type="button"
                  aria-label="Replay route animation"
                  onClick={() => routePlaybackRef.current?.play()}
                >
                  <RotateCcw size={13} />
                  Replay
                </button>
              )}
            </div>
          )}
        </div>

        <aside className="place-index route-sidebar" aria-label="Selected route details">
          <div className="route-sidebar-head">
            <span className="section-index">
              {isTransportation ? `${transportMode} route` : isFullTrip ? 'Full journey' : `Day ${activeRoute.day}`}
            </span>
            <h3>{activeRoute.title}</h3>
            {activeRoute.date && <p>{activeRoute.date}</p>}
          </div>
          {(formattedDistance || formattedDuration || formattedCost) && (
            <div className="route-metrics">
              {formattedDistance && <span>{formattedDistance}</span>}
              {formattedDuration && <span>{formattedDuration}</span>}
              {formattedCost && <span>{formattedCost}</span>}
            </div>
          )}
          <ol className="route-stops">
            {activeRoute.stops.map((stop, index) => (
              <li key={`${stop.role}-${stop.label}-${index}`}>
                <span className="place-number">{String(index + 1).padStart(2, '0')}</span>
                <span>
                  <strong>{stop.label}</strong>
                  <small>
                    {stop.type === 'restaurant'
                      ? TYPE_LABEL.restaurant
                      : ROLE_LABEL[stop.role] || TYPE_LABEL[stop.type] || stop.area || stop.type}
                    {stop.area && ` · ${stop.area}`}
                  </small>
                  {stop.star_rating != null && <small>★ {stop.star_rating} stars</small>}
                  {stop.ticket_price != null && <small>¥{stop.ticket_price} ticket</small>}
                  {stop.cuisine && <small>{stop.cuisine}</small>}
                  {stop.rating != null && <small>★ {stop.rating} rating</small>}
                  {stop.price != null && <small>¥{stop.price} avg</small>}
                  {stop.dish && <small>{stop.dish}</small>}
                  {index > 0 && routeSegmentDetails[index - 1] && (
                    <small className="route-segment-meta">
                      {routeSegmentDetails[index - 1].duration
                        ? `${formatDuration(routeSegmentDetails[index - 1].duration)} · `
                        : ''}
                      {routeSegmentDetails[index - 1].cost
                        ? `¥${Math.round(routeSegmentDetails[index - 1].cost)} est.`
                        : 'No fare'}
                    </small>
                  )}
                  <a
                    className="route-hint-btn"
                    href={index > 0
                      ? amapRouteUrl(activeRoute.stops[index - 1], stop, routeMode)
                      : amapPlaceUrl(stop)}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <Navigation size={11} />
                    {index > 0 ? `Route from ${activeRoute.stops[index - 1].label}` : 'Open in AMap'}
                  </a>
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
    </div>
  )
}
