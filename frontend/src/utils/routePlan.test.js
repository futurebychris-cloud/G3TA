import assert from 'node:assert/strict'
import test from 'node:test'

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

test('buildRouteModel maps known schedule activities and never invents unmatched stops', () => {
  const model = buildRouteModel(result)

  assert.deepEqual(model.days[0].stops.map((stop) => stop.label), [
    'Demo Hotel', 'Meiji Shrine', 'Demo Hotel',
  ])
  assert.deepEqual(model.days[1].stops.map((stop) => stop.label), ['Demo Hotel'])
  assert.equal(model.transportationRoute.stops.length, 2)
  assert.equal(model.transportationRoute.title, 'Transportation overview')
})

test('routeSegments creates each consecutive leg', () => {
  const model = buildRouteModel(result)
  assert.equal(routeSegments(model.days[0].stops).length, 2)
})

test('uniqueMarkerStops keeps the outbound and return stop numbers visible', () => {
  const model = buildRouteModel(result)
  const markers = uniqueMarkerStops(model.days[0].stops)

  assert.deepEqual(markers.map((marker) => marker.markerLabel), ['1/3', '2'])
})

test('projectPoints keeps all fallback markers inside the canvas', () => {
  const points = projectPoints(result.map_points, 800, 420, 56)
  points.forEach((point) => {
    assert.ok(point.x >= 56 && point.x <= 744)
    assert.ok(point.y >= 56 && point.y <= 364)
  })
})

test('projectPoints centers a route that only has one known stop', () => {
  const [point] = projectPoints([{ label: 'Hotel', lat: 35.7, lng: 139.7 }], 800, 420, 56)
  assert.equal(point.x, 400)
  assert.equal(point.y, 210)
})

test('formatDistance uses readable units', () => {
  assert.equal(formatDistance(850), '850 m')
  assert.equal(formatDistance(1250), '1.3 km')
})
