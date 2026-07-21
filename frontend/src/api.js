// Talks to the FastAPI backend. Uses the streaming endpoint so the UI can show
// each agent completing in real time (Server-Sent Events over a fetch stream).

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

// Streams the full plan. Calls onEvent(evt) for each SSE message:
//   {type:'agent_start', agent}
//   {type:'agent_done', agent, output?}
//   {type:'complete', result}
//   {type:'error', message}
export async function streamPlan(tripInput, onEvent) {
  const resp = await fetch(`${API_BASE}/plan/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(tripInput),
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
