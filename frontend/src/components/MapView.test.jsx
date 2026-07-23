import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'

import { ACCESSIBILITY_STORAGE_KEY, AccessibilityProvider } from '../accessibility/AccessibilityContext.jsx'
import { TextToSpeechProvider } from '../hooks/useTextToSpeech.js'
import MapView from './MapView.jsx'

const {
  animateMock,
  loadAmapMock,
  searchAmapSegmentMock,
} = vi.hoisted(() => ({
  animateMock: vi.fn(),
  loadAmapMock: vi.fn(),
  searchAmapSegmentMock: vi.fn(),
}))

vi.mock('motion', () => ({
  animate: animateMock,
}))

vi.mock('../lib/amap.js', () => ({
  hasAmapCredentials: () => true,
  loadAmap: loadAmapMock,
  searchAmapSegment: searchAmapSegmentMock,
}))

function createAmapMock() {
  const revealEvents = []
  let polylineId = 0
  const map = {
    add: vi.fn(),
    addControl: vi.fn(),
    clearMap: vi.fn(),
    destroy: vi.fn(),
    setFitView: vi.fn(),
  }
  return {
    api: {
      Map: vi.fn(function Map() { return map }),
      Marker: vi.fn(function Marker(options) {
        Object.assign(this, options)
        this.setPosition = vi.fn((position) => { this.position = position })
      }),
      Pixel: vi.fn(function Pixel(x, y) { Object.assign(this, { x, y }) }),
      Polyline: vi.fn(function Polyline(options) {
        Object.assign(this, options)
        this.id = ++polylineId
        this.hide = vi.fn()
        this.show = vi.fn()
        this.setOptions = vi.fn()
        this.setPath = vi.fn((path) => {
          this.path = path
          revealEvents.push({ id: this.id, path })
        })
      }),
      Scale: vi.fn(function Scale() {}),
      ToolBar: vi.fn(function ToolBar() {}),
    },
    map,
    revealEvents,
  }
}

function renderMap(result) {
  return render(
    <AccessibilityProvider>
      <TextToSpeechProvider>
        <MapView points={result.map_points} result={result} agentOutputs={result.agent_outputs} />
      </TextToSpeechProvider>
    </AccessibilityProvider>,
  )
}

const result = {
  destination: 'Shanghai',
  cost: { currency: 'CNY' },
  schedule: [
    {
      day: 1,
      date: '2026-08-10',
      title: 'Shanghai highlights',
      items: [{ type: 'activity', title: 'The Bund' }],
    },
    {
      day: 2,
      date: '2026-08-11',
      title: 'Old Shanghai',
      items: [{ type: 'activity', title: 'Yu Garden' }],
    },
    {
      day: 3,
      date: '2026-08-12',
      title: 'Culture',
      items: [{ type: 'activity', title: 'Shanghai Museum' }],
    },
  ],
  map_points: [
    { label: 'The Bund', type: 'activity', lat: 31.24, lng: 121.49 },
    { label: 'Yu Garden', type: 'activity', lat: 31.227, lng: 121.493 },
    { label: 'Shanghai Museum', type: 'activity', lat: 31.228, lng: 121.475 },
  ],
  agent_outputs: {
    transportation: {
      recommended: { type: 'train', from: 'Hangzhou', to: 'Shanghai' },
      route_points: [
        { label: 'Hangzhou East', type: 'transport', lat: 30.29, lng: 120.21 },
        { label: 'Shanghai Hongqiao', type: 'transport', lat: 31.20, lng: 121.32 },
      ],
    },
  },
}

describe('MapView AMap defaults', () => {
  let amapMock

  beforeEach(() => {
    amapMock = createAmapMock()
    loadAmapMock.mockResolvedValue(amapMock.api)
    animateMock.mockImplementation((from, to, options) => {
      const controls = { stop: vi.fn() }
      options.onUpdate?.(0)
      options.onUpdate?.(0.35)
      options.onUpdate?.(0.7)
      options.onUpdate?.(1)
      options.onComplete?.()
      return controls
    })
    searchAmapSegmentMock.mockImplementation((AMap, mode, from, to) => Promise.resolve({
      path: [
        [from.lng, from.lat],
        [(from.lng + to.lng) / 2, (from.lat + to.lat) / 2],
        [to.lng, to.lat],
      ],
      distance: 1800,
      duration: 1200,
    }))
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('reveals the full-trip route from the first stop to the final stop in order', async () => {
    renderMap(result)

    expect(await screen.findByText('AMap live')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Full trip' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Walking' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('region', { name: 'AMap route map' })).not.toHaveClass('hidden')
    await waitFor(() => expect(searchAmapSegmentMock).toHaveBeenCalledTimes(2))
    expect(await screen.findByText('Route traced')).toBeVisible()

    const firstPath = [
      [121.49, 31.24],
      [(121.49 + 121.493) / 2, (31.24 + 31.227) / 2],
      [121.493, 31.227],
    ]
    const secondPath = [
      [121.493, 31.227],
      [(121.493 + 121.475) / 2, (31.227 + 31.228) / 2],
      [121.475, 31.228],
    ]
    const firstPolyline = amapMock.api.Polyline.mock.results[0].value
    const secondPolyline = amapMock.api.Polyline.mock.results[1].value
    const firstCompleteEvent = amapMock.revealEvents.findIndex(({ id, path }) => (
      id === firstPolyline.id && JSON.stringify(path) === JSON.stringify(firstPath)
    ))
    const secondStartEvent = amapMock.revealEvents.findIndex(({ id }) => id === secondPolyline.id)

    expect(firstPolyline.setPath.mock.calls[0][0]).toEqual([
      firstPath[0], firstPath[0],
    ])
    expect(firstCompleteEvent).toBeGreaterThanOrEqual(0)
    expect(secondStartEvent).toBeGreaterThan(firstCompleteEvent)
    expect(firstPolyline.path).toEqual(firstPath)
    expect(secondPolyline.path).toEqual(secondPath)
    expect(secondPolyline.path.at(-1)).toEqual([121.475, 31.228])
    expect(searchAmapSegmentMock.mock.calls.every((call) => call[1] === 'walking')).toBe(true)
    expect(animateMock.mock.calls[0][2].duration).toBe(7.5)
    expect(screen.queryByRole('button', { name: 'Line preview' })).not.toBeInTheDocument()
  })

  it('replays the resolved path without requesting the AMap route again', async () => {
    const user = userEvent.setup()
    renderMap(result)

    expect(await screen.findByText('Route traced')).toBeVisible()
    expect(searchAmapSegmentMock).toHaveBeenCalledTimes(2)
    await user.click(screen.getByRole('button', { name: 'Replay route animation' }))

    await waitFor(() => expect(animateMock).toHaveBeenCalledTimes(2))
    expect(searchAmapSegmentMock).toHaveBeenCalledTimes(2)
  })

  it('requests a distinct driving route when the user switches mode', async () => {
    const user = userEvent.setup()
    renderMap(result)

    await screen.findByText('Live AMap walking route loaded successfully.')
    searchAmapSegmentMock.mockClear()
    await user.click(screen.getByRole('button', { name: 'Driving' }))

    await waitFor(() => expect(searchAmapSegmentMock).toHaveBeenCalledTimes(2))
    expect(searchAmapSegmentMock.mock.calls.every((call) => call[1] === 'driving')).toBe(true)
    expect(screen.getByText('Live AMap driving route loaded successfully.')).toBeVisible()
  })

  it('keeps successful routes separate when a middle AMap segment fails', async () => {
    const interruptedResult = {
      ...result,
      schedule: [
        { day: 1, items: [{ type: 'activity', title: 'A' }] },
        { day: 2, items: [{ type: 'activity', title: 'B' }] },
        { day: 3, items: [{ type: 'activity', title: 'C' }] },
        { day: 4, items: [{ type: 'activity', title: 'D' }] },
      ],
      map_points: [
        { label: 'A', type: 'activity', lat: 31.1, lng: 121.1 },
        { label: 'B', type: 'activity', lat: 31.2, lng: 121.2 },
        { label: 'C', type: 'activity', lat: 31.3, lng: 121.3 },
        { label: 'D', type: 'activity', lat: 31.4, lng: 121.4 },
      ],
    }
    const firstPath = [[121.1, 31.1], [121.15, 31.15], [121.2, 31.2]]
    const finalPath = [[121.3, 31.3], [121.35, 31.35], [121.4, 31.4]]
    searchAmapSegmentMock
      .mockResolvedValueOnce({ path: firstPath, distance: 1000, duration: 600 })
      .mockRejectedValueOnce(new Error('No walking route'))
      .mockResolvedValueOnce({ path: finalPath, distance: 1000, duration: 600 })

    renderMap(interruptedResult)

    expect(await screen.findByText('2 route segment(s) loaded; 1 AMap walking segment(s) are unavailable.')).toBeVisible()
    expect(amapMock.api.Polyline).toHaveBeenCalledTimes(2)
    expect(amapMock.api.Polyline.mock.results[0].value.path).toEqual(firstPath)
    expect(amapMock.api.Polyline.mock.results[1].value.path).toEqual(finalPath)
  })

  it('shows the complete route immediately when reduced motion is enabled', async () => {
    localStorage.setItem(ACCESSIBILITY_STORAGE_KEY, JSON.stringify({ reducedMotion: true }))
    renderMap(result)

    await screen.findByText('Live AMap walking route loaded successfully.')
    expect(animateMock).not.toHaveBeenCalled()
    expect(screen.getByText('Route traced')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Replay route animation' })).not.toBeInTheDocument()
    amapMock.api.Polyline.mock.results.forEach(({ value }) => {
      expect(value.setPath).toHaveBeenCalledWith(value.path)
    })
  })

  it('stops an in-progress route animation when the map unmounts', async () => {
    const stop = vi.fn()
    animateMock.mockReturnValue({ stop })
    const { unmount } = renderMap(result)

    await waitFor(() => expect(animateMock).toHaveBeenCalledOnce())
    unmount()

    expect(stop).toHaveBeenCalled()
    expect(amapMock.map.destroy).toHaveBeenCalledOnce()
  })

  it('switches from a day route to the live AMap transportation overview', async () => {
    const user = userEvent.setup()
    renderMap(result)

    await screen.findByText('AMap live')
    await user.click(screen.getByRole('button', { name: 'Train' }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'AMap overview' })).toHaveAttribute('aria-pressed', 'true')
    })
    expect(screen.getByText('AMap live')).toBeVisible()
  })
})
