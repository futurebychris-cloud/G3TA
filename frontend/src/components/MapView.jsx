import { useMemo, useState } from 'react'
import { BedDouble, Camera, MapPin } from 'lucide-react'
import { useAccessibilitySettings } from '../accessibility/AccessibilityContext.jsx'
import ReadAloudButton from './accessibility/ReadAloudButton.jsx'

const TYPE_META = {
  housing: { color: '#ff6b4a', label: 'Stay', icon: BedDouble },
  activity: { color: '#ccf06c', label: 'Experience', icon: Camera },
  transport: { color: '#80caff', label: 'Transit', icon: MapPin },
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

export default function MapView({ points, agentOutputs }) {
  const { settings } = useAccessibilitySettings()
  const [showAll, setShowAll] = useState(false)
  const isSenior = settings.preset === 'senior'
  const seniorChoices = useMemo(() => seniorRecommendations(points, agentOutputs), [points, agentOutputs])
  if (!points || points.length === 0) {
    return <div className="empty-state"><MapPin size={28} /><h3>No map points yet</h3><p>Locations will appear here when they are available.</p></div>
  }

  const lats = points.map((point) => point.lat)
  const lngs = points.map((point) => point.lng)
  const minLat = Math.min(...lats)
  const maxLat = Math.max(...lats)
  const minLng = Math.min(...lngs)
  const maxLng = Math.max(...lngs)
  const spanLat = maxLat - minLat || 1
  const spanLng = maxLng - minLng || 1

  const position = (point) => ({
    left: `${((point.lng - minLng) / spanLng) * 76 + 12}%`,
    top: `${(1 - (point.lat - minLat) / spanLat) * 72 + 14}%`,
  })
  const listEntries = isSenior && !showAll
    ? seniorChoices
    : points.map((point) => ({ point, recommendation: null }))

  return (
    <div className="places-view">
      <div className="panel-heading">
        <div><span className="section-index">YOUR PLACES</span><h2>Everything worth finding,<br />on one canvas.</h2></div>
        <p>An intentionally lightweight map preview built from the coordinates selected by your agents.</p>
      </div>
      <div className="result-heading-actions">
        <ReadAloudButton
          id="places-summary"
          label="recommended places"
          text={listEntries.flatMap(({ point, recommendation }, index) => [recommendation || `Place ${index + 1}`, point.label, TYPE_META[point.type]?.label || point.type, point.area])}
        />
      </div>

      <div className="places-layout">
        <div className="map-canvas" aria-hidden="true">
          <div className="map-noise" />
          <svg className="map-contours" viewBox="0 0 700 520" preserveAspectRatio="none" aria-hidden="true">
            <path d="M-20 122C106 26 222 196 348 89s239 18 381-31" />
            <path d="M-38 257c166-85 249 54 387-21s222 21 398-73" />
            <path d="M-20 402c106-69 213 39 334-44s266 49 431-35" />
            <path d="M113-20c58 104-20 199 55 307s8 180 36 264" />
            <path d="M406-20c-46 120 45 184-1 292s70 187 43 272" />
          </svg>
          <div className="map-grid-coordinates"><span>35°N</span><span>139°E</span></div>
          {points.map((point, index) => {
            const meta = TYPE_META[point.type] || TYPE_META.activity
            const PointIcon = meta.icon
            return (
              <div className="map-point" key={`${point.label}-${index}`} style={position(point)}>
                <span className="map-pin" style={{ '--pin-color': meta.color }}><PointIcon size={16} /></span>
                <span className="map-point-label"><small>{String(index + 1).padStart(2, '0')}</small>{point.label}</span>
              </div>
            )
          })}
        </div>

        <aside className="place-index" aria-labelledby="location-index-heading">
          <h3 className="section-index" id="location-index-heading">Location index</h3>
          <ol>
            {listEntries.map(({ point, recommendation }, index) => {
              const meta = TYPE_META[point.type] || TYPE_META.activity
              return (
                <li key={`${point.label}-list`}>
                  <span className="place-number">{String(index + 1).padStart(2, '0')}</span>
                  <span>
                    {recommendation && <small className="senior-choice-label">{recommendation}</small>}
                    <strong>{point.label}</strong>
                    <small>{meta.label}. {point.area || 'Area pending'}</small>
                  </span>
                </li>
              )
            })}
          </ol>
          {isSenior && points.length > seniorChoices.length && (
            <button className="show-more-results" type="button" aria-expanded={showAll} onClick={() => setShowAll((current) => !current)}>
              {showAll ? 'Show fewer places' : `Show all ${points.length} places`}
            </button>
          )}
          <p className="map-disclaimer">Relative coordinate preview. Live map tiles can be connected when your maps API is ready.</p>
        </aside>
      </div>
    </div>
  )
}
