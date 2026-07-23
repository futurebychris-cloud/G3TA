import { describe, expect, it } from 'vitest'

import {
  buildRouteModel,
  formatDistance,
  revealRoutePaths,
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
    expect(model.fullTripRoute.stops.map((stop) => stop.label)).toEqual([
      'Demo Hotel', 'Meiji Shrine', 'Demo Hotel',
    ])
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

  it('builds a full trip route in schedule order without requiring a hotel', () => {
    const model = buildRouteModel({
      schedule: [
        { day: 1, items: [{ type: 'activity', title: 'The Bund' }] },
        { day: 2, items: [{ type: 'activity', title: 'Yu Garden' }] },
        { day: 3, items: [{ type: 'activity', title: 'Shanghai Museum' }] },
      ],
      map_points: [
        { label: 'Shanghai Museum', type: 'activity', lat: 31.228, lng: 121.475 },
        { label: 'The Bund', type: 'activity', lat: 31.234, lng: 121.492 },
        { label: 'Yu Garden', type: 'activity', lat: 31.228, lng: 121.493 },
      ],
    })

    expect(model.fullTripRoute.stops.map((stop) => stop.label)).toEqual([
      'The Bund', 'Yu Garden', 'Shanghai Museum',
    ])
    expect(routeSegments(model.fullTripRoute.stops).map(({ from, to }) => [from.label, to.label])).toEqual([
      ['The Bund', 'Yu Garden'],
      ['Yu Garden', 'Shanghai Museum'],
    ])
  })

  it('includes restaurant stops from the latest backend in itinerary order', () => {
    const model = buildRouteModel({
      schedule: [{
        day: 1,
        items: [
          { type: 'meal', title: 'Morning Cafe' },
          { type: 'activity', title: 'West Lake' },
          { type: 'meal', title: 'Lakeview Restaurant' },
        ],
      }],
      map_points: [
        { label: 'West Lake', type: 'activity', lat: 30.25, lng: 120.15 },
        { label: 'Lakeview Restaurant', type: 'restaurant', lat: 30.26, lng: 120.16 },
        { label: 'Morning Cafe', type: 'restaurant', lat: 30.24, lng: 120.14 },
      ],
    })

    expect(model.fullTripRoute.stops.map((stop) => [stop.label, stop.role])).toEqual([
      ['Morning Cafe', 'meal'],
      ['West Lake', 'visit'],
      ['Lakeview Restaurant', 'meal'],
    ])
  })

  it('falls back to mappable activity and restaurant order when no schedule is available', () => {
    const model = buildRouteModel({
      map_points: [
        { label: 'Hotel', type: 'housing', lat: 30.23, lng: 120.13 },
        { label: 'Museum', type: 'activity', lat: 30.24, lng: 120.14 },
        { label: 'Dinner', type: 'restaurant', lat: 30.25, lng: 120.15 },
      ],
    })

    expect(model.fullTripRoute.stops.map((stop) => stop.label)).toEqual([
      'Hotel', 'Museum', 'Dinner', 'Hotel',
    ])
  })

  it('does not reuse a generic city-center pin for named itinerary stops', () => {
    const model = buildRouteModel({
      schedule: [
        { day: 1, items: [{ type: 'activity', title: 'Shanghai Museum' }] },
        { day: 2, items: [{ type: 'activity', title: 'Shanghai Natural History Museum' }] },
      ],
      map_points: [{
        label: 'Shanghai',
        type: 'activity',
        area: 'Shanghai',
        lat: 31.231,
        lng: 121.47,
        description: 'City center',
      }],
    })

    expect(model.days.every((day) => day.stops.length === 0)).toBe(true)
    expect(model.fullTripRoute.stops.map((stop) => stop.label)).toEqual(['Shanghai'])
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

  it('formats distance with readable units', () => {
    expect(formatDistance(850)).toBe('850 m')
    expect(formatDistance(1250)).toBe('1.3 km')
  })

  it('reveals consecutive route paths from the first point to the final point', () => {
    const paths = [
      [[0, 0], [1, 0], [2, 0]],
      [[2, 0], [2, 1], [2, 2]],
    ]

    expect(revealRoutePaths(paths, 0)).toEqual([[[0, 0]], []])
    expect(revealRoutePaths(paths, 0.375)).toEqual([
      [[0, 0], [1, 0], [1.5, 0]],
      [],
    ])
    expect(revealRoutePaths(paths, 0.625)).toEqual([
      [[0, 0], [1, 0], [2, 0]],
      [[2, 0], [2, 0.5]],
    ])
    expect(revealRoutePaths(paths, 1)).toEqual(paths)
  })
})
