import { BedDouble, Camera, MapPin } from 'lucide-react'

const TYPE_META = {
  housing: { color: '#ff6b4a', label: 'Stay', icon: BedDouble },
  activity: { color: '#ccf06c', label: 'Experience', icon: Camera },
  transport: { color: '#80caff', label: 'Transit', icon: MapPin },
}

export default function MapView({ points }) {
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

  return (
    <div className="places-view">
      <div className="panel-heading">
        <div><span className="section-index">YOUR PLACES</span><h2>Everything worth finding,<br />on one canvas.</h2></div>
        <p>An intentionally lightweight map preview built from the coordinates selected by your agents.</p>
      </div>

      <div className="places-layout">
        <div className="map-canvas" aria-label="Map of recommended trip points">
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

        <aside className="place-index">
          <span className="section-index">LOCATION INDEX</span>
          <ol>
            {points.map((point, index) => {
              const meta = TYPE_META[point.type] || TYPE_META.activity
              return (
                <li key={`${point.label}-list`}>
                  <span className="place-number">{String(index + 1).padStart(2, '0')}</span>
                  <span><strong>{point.label}</strong><small>{meta.label} · {point.area || 'Area pending'}</small></span>
                </li>
              )
            })}
          </ol>
          <p className="map-disclaimer">Relative coordinate preview. Live map tiles can be connected when your maps API is ready.</p>
        </aside>
      </div>
    </div>
  )
}
