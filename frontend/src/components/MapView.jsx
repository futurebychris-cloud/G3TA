// Static map placeholder (PRD §9 / §15 decision: static component for MVP).
// Plots pins by relative lat/lng in a self-contained box — no external tiles or
// API key. A teammate can swap this for Leaflet later without touching the data.
const TYPE_COLOR = { housing: '#e11d48', activity: '#2563eb', transport: '#059669' }

export default function MapView({ points }) {
  if (!points || points.length === 0) {
    return <p className="muted">No map points available.</p>
  }

  const lats = points.map((p) => p.lat)
  const lngs = points.map((p) => p.lng)
  const minLat = Math.min(...lats)
  const maxLat = Math.max(...lats)
  const minLng = Math.min(...lngs)
  const maxLng = Math.max(...lngs)
  const spanLat = maxLat - minLat || 1
  const spanLng = maxLng - minLng || 1

  const pos = (p) => ({
    left: `${((p.lng - minLng) / spanLng) * 90 + 5}%`,
    // Higher latitude = further north = nearer the top.
    top: `${(1 - (p.lat - minLat) / spanLat) * 90 + 5}%`,
  })

  return (
    <div>
      <div className="map-box" aria-label="Static map of trip points">
        <div className="map-grid" />
        {points.map((p, i) => (
          <div key={i} className="pin" style={{ ...pos(p), background: TYPE_COLOR[p.type] || '#666' }} title={`${p.label} (${p.area || ''})`}>
            <span className="pin-label">{p.label}</span>
          </div>
        ))}
      </div>
      <p className="muted map-note">Static placeholder map — pins positioned by relative coordinates. Swap for Leaflet post-MVP.</p>
      <ul className="legend">
        {Object.entries(TYPE_COLOR).map(([type, color]) => (
          <li key={type}><span className="swatch" style={{ background: color }} /> {type}</li>
        ))}
      </ul>
    </div>
  )
}
