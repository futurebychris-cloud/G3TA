// Talks to the FastAPI backend. Uses the streaming endpoint so the UI can show
// each agent completing in real time (Server-Sent Events over a fetch stream).

const API_BASE = import.meta.env.VITE_API_BASE || ''

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
      onEvent(payload)
    }
  }
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

// Confirm a selected hotel: drive the Ctrip Playwright booking to the payment step.
export async function confirmBooking(req) {
  const resp = await fetch(`${API_BASE}/booking/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!resp.ok) {
    const detail = await resp.text().catch(() => resp.statusText)
    throw new Error(`Booking confirm failed (${resp.status}): ${detail}`)
  }
  return resp.json()
}

// Mark a stored route as paid (user paid in their own WeChat/Alipay).
export async function markBookingPaid(routeId, orderNo) {
  const resp = await fetch(`${API_BASE}/booking/mark_paid`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ route_id: routeId, order_no: orderNo }),
  })
  if (!resp.ok) {
    const detail = await resp.text().catch(() => resp.statusText)
    throw new Error(`Mark paid failed (${resp.status}): ${detail}`)
  }
  return resp.json()
}

// List all stored confirmed routes (audit trail).
export async function getBookingRoutes() {
  const resp = await fetch(`${API_BASE}/booking/routes`)
  if (!resp.ok) throw new Error(`Failed to load routes (${resp.status})`)
  return resp.json()
}

// Fetch all checklist items for a trip from the shared_checklist database.
export async function getChecklist(tripId) {
  const resp = await fetch(`${API_BASE}/api/checklist/${tripId}`)
  if (!resp.ok) throw new Error(`Failed to load checklist (${resp.status})`)
  return resp.json()
}

// Toggle a checklist item's is_packed status.
export async function toggleChecklistItem(itemId, isPacked) {
  const resp = await fetch(`${API_BASE}/api/checklist/${itemId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ is_packed: isPacked }),
  })
  if (!resp.ok) throw new Error(`Failed to update checklist item (${resp.status})`)
  return resp.json()
}
