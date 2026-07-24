// Talks to the FastAPI backend. Uses the streaming endpoint so the UI can show
// each agent completing in real time (Server-Sent Events over a fetch stream).

const API_BASE = import.meta.env.VITE_API_BASE || ''

// Shared secret required by the backend for any booking write (configured via
// BOOKING_API_TOKEN). Sent as the X-G3TA-Booking-Token header. Leave it blank
// only for a trusted localhost demo where the backend allows localhost.
const BOOKING_TOKEN = import.meta.env.VITE_G3TA_BOOKING_TOKEN || ''
function bookingHeaders() {
  const headers = { 'Content-Type': 'application/json' }
  if (BOOKING_TOKEN) headers['X-G3TA-Booking-Token'] = BOOKING_TOKEN
  return headers
}

export async function getHealth() {
  const resp = await fetch(`${API_BASE}/health`)
  if (!resp.ok) throw new Error(`Health check failed (${resp.status})`)
  return resp.json()
}


export async function parseTripDescription(description, { signal } = {}) {
  const resp = await fetch(`${API_BASE}/intake/parse`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ description }),
    signal,
  })
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}))
    throw new Error(body.detail || `Trip assistant failed (${resp.status})`)
  }
  return resp.json()
}


export async function synthesizeSpeech(text, speed = 1, { signal } = {}) {
  const language = /[\u3400-\u9fff]/u.test(String(text)) ? 'zh' : 'en'
  const resp = await fetch(`${API_BASE}/speech/synthesize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, speed, language }),
    signal,
  })
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}))
    throw new Error(body.detail || `Read aloud failed (${resp.status})`)
  }
  return resp.blob()
}

// Streams the full plan. Calls onEvent(evt) for each SSE message:
//   {type:'agent_start', agent}
//   {type:'agent_done', agent, output?}
//   {type:'complete', result}
//   {type:'error', message}
export async function streamPlan(tripInput, onEvent, { signal } = {}) {
  const resp = await fetch(`${API_BASE}/plan/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(tripInput),
    signal,
  })

  if (!resp.ok || !resp.body) {
    const detail = await resp.text().catch(() => resp.statusText)
    throw new Error(`Backend error (${resp.status}): ${detail}`)
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let sawTerminalEvent = false

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // SSE messages are separated by a blank line.
    const chunks = buffer.split('\n\n')
    buffer = chunks.pop() // keep the trailing partial message
    for (const chunk of chunks) {
      const line = chunk.split('\n').find((l) => l.startsWith('data:'))
      if (!line) continue
      const payload = JSON.parse(line.slice(5).trim())
      if (['complete', 'error', 'cancelled'].includes(payload.type)) {
        sawTerminalEvent = true
      }
      onEvent(payload)
    }
  }
  if (!sawTerminalEvent && !signal?.aborted) {
    throw new Error('The planning stream ended before a result was returned. Please retry.')
  }
}


export async function cancelPlan(requestId, { keepalive = false } = {}) {
  const resp = await fetch(`${API_BASE}/plan/cancel/${encodeURIComponent(requestId)}`, {
    method: 'POST',
    keepalive,
  })
  if (!resp.ok && resp.status !== 404) {
    throw new Error(`Cancel failed (${resp.status})`)
  }
  return resp.ok ? resp.json() : { request_id: requestId, status: 'finished' }
}


export async function finalizePlan(trip, existingResult, adjustedBudget, { signal } = {}) {
  const resp = await fetch(`${API_BASE}/plan/finalize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      trip,
      existing_result: existingResult,
      adjusted_budget: adjustedBudget || undefined,
    }),
    signal,
  })
  if (!resp.ok) {
    const detail = await resp.text().catch(() => resp.statusText)
    throw new Error(`Finalize failed (${resp.status}): ${detail}`)
  }
  return resp.json()
}

// Streams the 4-stage hotel booking search. Calls onEvent(evt) for each SSE message:
//   {type:'booking_stage', stage:'search'|'filtering'|'outputting', status, source?, count?}
//   {type:'booking_results', hotels:[...]}
//   {type:'error', message}
export async function streamBookingSearch(req, onEvent) {
  const resp = await fetch(`${API_BASE}/booking/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!resp.ok || !resp.body) {
    const detail = await resp.text().catch(() => resp.statusText)
    throw new Error(`Backend error (${resp.status}): ${detail}`)
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const chunks = buffer.split('\n\n')
    buffer = chunks.pop()
    for (const chunk of chunks) {
      const line = chunk.split('\n').find((l) => l.startsWith('data:'))
      if (!line) continue
      const payload = JSON.parse(line.slice(5).trim())
      onEvent(payload)
    }
  }
}

// Fetch all checklist items for a trip from the shared_checklist database.
export async function getChecklist(tripId) {
  const resp = await fetch(`${API_BASE}/api/checklist/${tripId}`)
  if (!resp.ok) throw new Error(`Failed to load checklist (${resp.status})`)
  return resp.json()
}

// Toggle a checklist item's is_packed status.
export async function toggleChecklistItem(itemId, tripId, isPacked) {
  const resp = await fetch(`${API_BASE}/api/checklist/${itemId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ trip_id: tripId, is_packed: isPacked }),
  })
  if (!resp.ok) throw new Error(`Failed to update checklist item (${resp.status})`)
  return resp.json()
}

// --- Cookie-backed result persistence -------------------------------------- //

export async function saveResult(result, input, tripId) {
  const resp = await fetch(`${API_BASE}/api/results/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ result, input: input || undefined, trip_id: tripId || undefined }),
  })
  if (!resp.ok) {
    const detail = await resp.text().catch(() => resp.statusText)
    throw new Error(`Save result failed (${resp.status}): ${detail}`)
  }
  return resp.json()
}

export async function loadResult(tripId) {
  const resp = await fetch(`${API_BASE}/api/results/load?trip_id=${encodeURIComponent(tripId)}`, {
    credentials: 'include',
  })
  if (!resp.ok) throw new Error(`Load result failed (${resp.status})`)
  return resp.json()
}

export async function loadLatestResult() {
  const resp = await fetch(`${API_BASE}/api/results/latest`, { credentials: 'include' })
  if (!resp.ok) throw new Error(`Load result failed (${resp.status})`)
  return resp.json()
}

// --- Ctrip session cookies + real hotel images ----------------------------- //

export async function saveCookies(cookieString) {
  const resp = await fetch(`${API_BASE}/booking/cookies`, {
    method: 'POST',
    headers: bookingHeaders(),
    credentials: 'include',
    body: JSON.stringify({ cookie_string: cookieString }),
  })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({}))
    throw new Error(detail.detail || `Save cookies failed (${resp.status})`)
  }
  return resp.json()
}

export async function fetchHotelImages({ url = '', hotel_id = '', max_images = 6 }) {
  const resp = await fetch(`${API_BASE}/booking/hotel-images`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ url, hotel_id, max_images }),
  })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({}))
    throw new Error(detail.detail || `Image scrape failed (${resp.status})`)
  }
  return resp.json()
}

export async function autoBookHotel(payload) {
  const resp = await fetch(`${API_BASE}/booking/auto/hotel`, {
    method: 'POST',
    headers: bookingHeaders(),
    credentials: 'include',
    body: JSON.stringify(payload),
  })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({}))
    throw new Error(detail.detail || `Auto-book failed (${resp.status})`)
  }
  return resp.json()
}
