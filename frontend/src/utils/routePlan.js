function validPoint(point) {
  const latitude = Number(point?.lat)
  const longitude = Number(point?.lng)
  return point
    && Number.isFinite(latitude)
    && Number.isFinite(longitude)
    && latitude >= -90
    && latitude <= 90
    && longitude >= -180
    && longitude <= 180
}

function normalizeLabel(value) {
  return String(value || '').trim().toLocaleLowerCase().replace(/\s+/g, ' ')
}

function findPoint(label, points) {
  const wanted = normalizeLabel(label)
  if (!wanted) return null
  return points.find((point) => {
    const candidate = normalizeLabel(point.label)
    return candidate === wanted || candidate.includes(wanted) || wanted.includes(candidate)
  }) || null
}

function uniquePoints(points) {
  const seen = new Set()
  return points.filter((point) => {
    const key = `${point.label}:${point.lng}:${point.lat}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

export function buildRouteModel(result = {}) {
  const mapPoints = (result.map_points || []).filter(validPoint).map((point) => ({
    ...point,
    lat: Number(point.lat),
    lng: Number(point.lng),
  }))
  const housing = mapPoints.find((point) => point.type === 'housing') || null
  const activities = mapPoints.filter((point) => point.type === 'activity')
  const transportation = result.agent_outputs?.transportation || {}
  const transportPoints = (transportation.route_points || []).filter(validPoint).map((point) => ({
    ...point,
    lat: Number(point.lat),
    lng: Number(point.lng),
  }))
  const transportMode = String(
    transportation.route_summary?.mode || transportation.recommended?.mode || 'transportation',
  ).trim().toLowerCase()
  const transportLabel = transportMode.charAt(0).toUpperCase() + transportMode.slice(1)

  const days = (result.schedule || []).map((day, dayIndex) => {
    const itemMatches = (day.items || [])
      .filter((item) => item.type === 'activity')
      .map((item) => findPoint(item.title, activities))
      .filter(Boolean)
    const titleMatch = findPoint(day.title, activities)
    const dayActivities = uniquePoints(itemMatches.length ? itemMatches : [titleMatch].filter(Boolean))

    const stops = []
    if (housing) stops.push({ ...housing, role: 'start' })
    dayActivities.forEach((point) => stops.push({ ...point, role: 'visit' }))
    if (housing && dayActivities.length) stops.push({ ...housing, role: 'return' })

    return {
      id: `day-${day.day ?? dayIndex + 1}`,
      day: day.day ?? dayIndex + 1,
      date: day.date,
      title: day.title || `Day ${dayIndex + 1}`,
      items: day.items || [],
      stops,
    }
  })

  return {
    days,
    transportationRoute: {
      id: 'transportation',
      mode: transportMode,
      title: `${transportLabel} overview`,
      stops: transportPoints,
    },
    transportation,
  }
}

export function routeSegments(stops = []) {
  return stops.slice(0, -1).map((from, index) => ({ from, to: stops[index + 1] }))
}

export function uniqueMarkerStops(stops = []) {
  const markers = new Map()
  stops.forEach((point, index) => {
    const key = `${point.label}:${point.lng}:${point.lat}`
    const existing = markers.get(key)
    if (existing) {
      existing.markerLabel = `${existing.markerLabel}/${index + 1}`
    } else {
      markers.set(key, { ...point, markerLabel: String(index + 1) })
    }
  })
  return [...markers.values()]
}

export function projectPoints(points = [], width = 800, height = 420, padding = 56) {
  if (!points.length) return []
  const lngs = points.map((point) => Number(point.lng))
  const lats = points.map((point) => Number(point.lat))
  const minLng = Math.min(...lngs)
  const maxLng = Math.max(...lngs)
  const minLat = Math.min(...lats)
  const maxLat = Math.max(...lats)
  const lngSpan = maxLng - minLng
  const latSpan = maxLat - minLat

  return points.map((point) => ({
    ...point,
    x: lngSpan === 0
      ? width / 2
      : padding + ((Number(point.lng) - minLng) / lngSpan) * (width - padding * 2),
    y: latSpan === 0
      ? height / 2
      : padding + (1 - (Number(point.lat) - minLat) / latSpan) * (height - padding * 2),
  }))
}

export function formatDistance(metres) {
  if (!Number.isFinite(metres) || metres <= 0) return null
  return metres >= 1000 ? `${(metres / 1000).toFixed(1)} km` : `${Math.round(metres)} m`
}

export function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds <= 0) return null
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min`
  const hours = Math.floor(minutes / 60)
  return `${hours} h ${minutes % 60} min`
}
