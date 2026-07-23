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
    if (candidate === wanted) return true
    if (normalizeLabel(point.description) === 'city center') return false
    const shorterLength = Math.min(candidate.length, wanted.length)
    const longerLength = Math.max(candidate.length, wanted.length)
    return shorterLength >= 4
      && shorterLength / longerLength >= 0.6
      && (candidate.includes(wanted) || wanted.includes(candidate))
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
  const restaurants = mapPoints.filter((point) => point.type === 'restaurant')
  const transportation = result.agent_outputs?.transportation || {}
  const explicitTransportPoints = (transportation.route_points || []).filter(validPoint)
  const mappedTransportPoints = mapPoints.filter((point) => point.type === 'transport')
  const rawTransportPoints = explicitTransportPoints.length ? explicitTransportPoints : mappedTransportPoints
  const transportPoints = rawTransportPoints.map((point, index) => ({
    ...point,
    lat: Number(point.lat),
    lng: Number(point.lng),
    role: point.role || (index === 0 ? 'departure' : index === rawTransportPoints.length - 1 ? 'arrival' : 'transfer'),
  }))
  const transportMode = String(
    transportation.route_summary?.mode
      || transportation.recommended?.mode
      || transportation.recommended?.type
      || 'transportation',
  ).trim().toLowerCase()
  const transportLabel = transportMode.charAt(0).toUpperCase() + transportMode.slice(1)

  const days = (result.schedule || []).map((day, dayIndex) => {
    const itemMatches = (day.items || [])
      .map((item) => {
        if (item.type === 'activity') return findPoint(item.title, activities)
        if (item.type === 'meal') return findPoint(item.title, restaurants)
        return null
      })
      .filter(Boolean)
    const titleMatch = findPoint(day.title, activities)
    const dayActivities = uniquePoints(itemMatches.length ? itemMatches : [titleMatch].filter(Boolean))

    const stops = []
    if (housing) stops.push({ ...housing, role: 'start' })
    dayActivities.forEach((point) => stops.push({
      ...point,
      role: point.type === 'restaurant' ? 'meal' : 'visit',
    }))
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
  const scheduledStops = days.flatMap((day) => (
    day.stops
      .filter((point) => point.role === 'visit' || point.role === 'meal')
  ))
  const itineraryStops = scheduledStops.length
    ? scheduledStops
    : mapPoints
      .filter((point) => point.type === 'activity' || point.type === 'restaurant')
      .map((point) => ({ ...point, role: point.type === 'restaurant' ? 'meal' : 'visit' }))
  const fullTripStops = []
  if (housing) fullTripStops.push({ ...housing, role: 'start' })
  fullTripStops.push(...itineraryStops)
  if (housing && itineraryStops.length) fullTripStops.push({ ...housing, role: 'return' })

  return {
    days,
    fullTripRoute: {
      id: 'full-trip',
      title: 'Full trip route',
      stops: fullTripStops,
    },
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

export function revealRoutePaths(paths = [], progress = 1) {
  const numericProgress = Number(progress)
  const normalizedProgress = Number.isFinite(numericProgress)
    ? Math.min(1, Math.max(0, numericProgress))
    : 0
  const edgeCounts = paths.map((path) => Math.max(0, path.length - 1))
  const totalEdges = edgeCounts.reduce((sum, count) => sum + count, 0)
  if (!totalEdges) return paths.map((path, index) => (index === 0 ? path.slice(0, 1) : []))

  const travelledEdges = normalizedProgress * totalEdges
  let consumedEdges = 0

  return paths.map((path, pathIndex) => {
    const edgeCount = edgeCounts[pathIndex]
    if (!edgeCount) return travelledEdges >= consumedEdges ? path.slice(0, 1) : []
    if (travelledEdges < consumedEdges) {
      consumedEdges += edgeCount
      return []
    }

    const localProgress = Math.min(edgeCount, travelledEdges - consumedEdges)
    consumedEdges += edgeCount
    if (localProgress >= edgeCount) return path.slice()

    const completeEdges = Math.floor(localProgress)
    const partialProgress = localProgress - completeEdges
    const visiblePath = path.slice(0, completeEdges + 1)
    if (partialProgress > 0 && path[completeEdges + 1]) {
      const from = path[completeEdges]
      const to = path[completeEdges + 1]
      visiblePath.push([
        Number(from[0]) + (Number(to[0]) - Number(from[0])) * partialProgress,
        Number(from[1]) + (Number(to[1]) - Number(from[1])) * partialProgress,
      ])
    }
    return visiblePath
  })
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
