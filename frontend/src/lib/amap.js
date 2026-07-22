import AMapLoader from '@amap/amap-jsapi-loader'

let amapPromise = null

export function hasAmapCredentials(key, securityCode) {
  return Boolean(key?.trim() && securityCode?.trim())
}

export function loadAmap(key, securityCode) {
  if (!hasAmapCredentials(key, securityCode)) {
    return Promise.reject(new Error('AMap Web key and security code are required.'))
  }

  window._AMapSecurityConfig = { securityJsCode: securityCode }
  if (!amapPromise) {
    amapPromise = AMapLoader.load({
      key,
      version: '2.0',
      plugins: ['AMap.Scale', 'AMap.ToolBar', 'AMap.Driving', 'AMap.Walking'],
    }).catch((error) => {
      amapPromise = null
      throw error
    })
  }
  return amapPromise
}

function toCoordinate(point) {
  if (Array.isArray(point)) return point
  if (typeof point?.getLng === 'function') return [point.getLng(), point.getLat()]
  return [Number(point.lng), Number(point.lat)]
}

export function searchAmapSegment(AMap, mode, from, to) {
  const Planner = mode === 'driving' ? AMap.Driving : AMap.Walking
  if (!Planner) return Promise.reject(new Error(`AMap ${mode} plugin is unavailable.`))

  const options = { hideMarkers: true, autoFitView: false }
  if (mode === 'driving' && AMap.DrivingPolicy) {
    options.policy = AMap.DrivingPolicy.LEAST_TIME
  }
  const planner = new Planner(options)

  return new Promise((resolve, reject) => {
    planner.search(
      new AMap.LngLat(from.lng, from.lat),
      new AMap.LngLat(to.lng, to.lat),
      (status, response) => {
        if (status !== 'complete' || !response?.routes?.length) {
          reject(new Error(response?.info || `AMap returned ${status}.`))
          return
        }
        const route = response.routes[0]
        const path = (route.steps || []).flatMap((step) => (step.path || []).map(toCoordinate))
        if (path.length < 2) {
          reject(new Error('AMap returned a route without drawable path points.'))
          return
        }
        resolve({
          path,
          distance: Number(route.distance) || 0,
          duration: Number(route.time) || 0,
        })
      },
    )
  })
}
