import { describe, expect, it } from 'vitest'

import {
  buildRouteModel,
  formatDistance,
  projectPoints,
  routeSegments,
  uniqueMarkerStops,
} from './routePlan.js'

const result = {
  schedule: [
    { day: 1, date: '2026-04-10', title: 'Meiji Shrine', items: [{ type: 'activity', title: 'Meiji Shrine' }] },
    { day: 2, date: '2026-04-11', title: 'Fallback day', items: [] },
  ],
  map_points: [
    { label: 'Demo Hotel', type: 'housing', lat: 35.7, lng: 139.7 },
    { label: 'Meiji Shrine', type: 'activity', lat: 35.67, lng: 139.69 },
    { label: 'Tokyo Tower', type: 'activity', lat: 35.65, lng: 139.74 },
  ],
  agent_outputs: {
    transportation: {
      route_points: [
        { label: 'JFK', type: 'transport', lat: 40.64, lng: -73.77 },
        { label: 'NRT', type: 'transport', lat: 35.77, lng: 140.39 },
      ],
    },
  },
}

describe('route planning helpers', () => {
  it('maps known schedule activities and never invents unmatched stops', () => {
    const model = buildRouteModel(result)

    expect(model.days[0].stops.map((stop) => stop.label)).toEqual([
      'Demo Hotel', 'Meiji Shrine', 'Demo Hotel',
    ])
    expect(model.days[1].stops.map((stop) => stop.label)).toEqual(['Demo Hotel'])
    expect(model.transportationRoute.stops).toHaveLength(2)
    expect(model.transportationRoute.title).toBe('Transportation overview')
  })

  it('creates each consecutive route leg', () => {
    const model = buildRouteModel(result)
    expect(routeSegments(model.days[0].stops)).toHaveLength(2)
  })

  it('keeps the outbound and return stop numbers visible', () => {
    const model = buildRouteModel(result)
    const markers = uniqueMarkerStops(model.days[0].stops)

    expect(markers.map((marker) => marker.markerLabel)).toEqual(['1/3', '2'])
  })

  it('keeps all fallback markers inside the canvas', () => {
    const points = projectPoints(result.map_points, 800, 420, 56)
    points.forEach((point) => {
      expect(point.x).toBeGreaterThanOrEqual(56)
      expect(point.x).toBeLessThanOrEqual(744)
      expect(point.y).toBeGreaterThanOrEqual(56)
      expect(point.y).toBeLessThanOrEqual(364)
    })
  })

  it('rejects out-of-range coordinates before building routes', () => {
    const model = buildRouteModel({
      schedule: [{ day: 1, title: 'Safe day', items: [
        { type: 'activity', title: 'Invalid stop' },
        { type: 'activity', title: 'Valid stop' },
      ] }],
      map_points: [
        { label: 'Invalid stop', type: 'activity', lat: 120, lng: 139.7 },
        { label: 'Valid stop', type: 'activity', lat: 35.7, lng: 139.7 },
      ],
    })
    expect(model.days[0].stops.map((stop) => stop.label)).toEqual(['Valid stop'])
  })

  it('uses transport map points from the latest backend when route_points are absent', () => {
    const model = buildRouteModel({
      map_points: [
        { label: 'Hangzhou', type: 'transport', lat: 30.2741, lng: 120.1551 },
        { label: 'New York', type: 'transport', lat: 40.7128, lng: -74.006 },
      ],
      agent_outputs: { transportation: { recommended: { type: 'flight' } } },
    })

    expect(model.transportationRoute.title).toBe('Flight overview')
    expect(model.transportationRoute.stops.map((stop) => stop.role)).toEqual(['departure', 'arrival'])
  })

  it('centers a route that only has one known stop', () => {
    const [point] = projectPoints([{ label: 'Hotel', lat: 35.7, lng: 139.7 }], 800, 420, 56)
    expect(point.x).toBe(400)
    expect(point.y).toBe(210)
  })

  it('formats distance with readable units', () => {
    expect(formatDistance(850)).toBe('850 m')
    expect(formatDistance(1250)).toBe('1.3 km')
  })
})
