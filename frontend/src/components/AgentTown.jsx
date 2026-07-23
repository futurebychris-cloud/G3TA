const TOWN_META = {
  budget: {
    label: 'Budget architect', short: 'BUD', color: '#ffca6b', x: 15, y: 31,
    running: 'Splitting the shared budget into clear limits.',
    done: 'Budget caps are pinned to the town board.',
  },
  transportation: {
    label: 'Route scout', short: 'RTE', color: '#80caff', x: 34, y: 24,
    running: 'Comparing routes, times, and arrival points.',
    done: 'The recommended route is on its way to Town Hall.',
  },
  housing: {
    label: 'Stay curator', short: 'STY', color: '#ff9277', x: 84, y: 31,
    running: 'Checking stays against place, price, and pace.',
    done: 'A short list of stays has reached the shared table.',
  },
  food: {
    label: 'Taste editor', short: 'EAT', color: '#cef26f', x: 15, y: 64,
    running: 'Pairing every day with meals that fit the brief.',
    done: 'The meal plan is ready for the other agents.',
  },
  activity: {
    label: 'Experience scout', short: 'EXP', color: '#b9a4ff', x: 84, y: 64,
    running: 'Curating memorable stops without crowding the day.',
    done: 'The activity sequence has been handed off.',
  },
  planning: {
    label: 'Journey editor', short: 'PLN', color: '#f4a7d1', x: 34, y: 67,
    running: 'Balancing weather, pacing, and what to pack.',
    done: 'Daily pacing notes are now on the planning table.',
  },
  orchestrator: {
    label: 'Lead orchestrator', short: 'LEAD', color: '#ff6847', x: 53, y: 48,
    running: 'Reading every handoff and resolving trade-offs.',
    done: 'The whole town agrees. Your journey is ready.',
  },
}

function truncate(text, limit = 92) {
  if (typeof text !== 'string') return ''
  const clean = text.replace(/\s+/g, ' ').trim()
  return clean.length > limit ? `${clean.slice(0, limit - 1)}…` : clean
}

function eventMessage(event) {
  const meta = TOWN_META[event?.agent]
  if (!meta) return ''
  if (event.type === 'start') return meta.running
  const output = event.output || {}
  return truncate(output.reasoning || output.pacing_notes) || meta.done
}

function PixelResident({ color, status }) {
  return (
    <span
      className={`town-pixel-resident town-pixel-resident--${status}`}
      style={{ '--agent-color': color }}
      aria-hidden="true"
    >
      <span className="town-pixel-hair" />
      <span className="town-pixel-head">
        <span className="town-pixel-eye town-pixel-eye--left" />
        <span className="town-pixel-eye town-pixel-eye--right" />
      </span>
      <span className="town-pixel-body" />
      <span className="town-pixel-arm town-pixel-arm--left" />
      <span className="town-pixel-arm town-pixel-arm--right" />
      <span className="town-pixel-leg town-pixel-leg--left" />
      <span className="town-pixel-leg town-pixel-leg--right" />
    </span>
  )
}

function TownBuilding({ className, label }) {
  return (
    <div className={`town-building ${className}`} aria-hidden="true">
      <span className="town-building-roof" />
      <span className="town-building-window town-building-window--left" />
      <span className="town-building-window town-building-window--right" />
      <span className="town-building-door" />
      <small>{label}</small>
    </div>
  )
}

export default function AgentTown({ agents, statuses, events = [], trip = null, paused = false }) {
  const visibleAgents = agents.filter((agent) => TOWN_META[agent])
  const knownEvents = events.filter((event) => TOWN_META[event?.agent])
  const latestEvent = knownEvents[knownEvents.length - 1]
  const statusFor = (agent) => (
    paused && statuses[agent] === 'running' ? 'paused' : (statuses[agent] || 'pending')
  )
  const doneCount = visibleAgents.filter((agent) => statusFor(agent) === 'done').length
  const runningCount = visibleAgents.filter((agent) => statusFor(agent) === 'running').length
  const channelEvents = knownEvents.slice(-3)
  const origin = trip?.origin || 'Origin'
  const destination = trip?.location || 'Destination'

  return (
    <section className="agent-town" aria-label="Live Agent Town planning session">
      <div className="town-scene-head">
        <div>
          <span className="section-index">AGENT TOWN · LIVE</span>
          <h2>The crew is building<br /><em>your journey.</em></h2>
        </div>
        <div className="town-mission-chip" aria-label={`Planning from ${origin} to ${destination}`}>
          <span>{origin}</span><b aria-hidden="true">→</b><span>{destination}</span>
        </div>
      </div>

      <div className="town-scene">
        <div className="town-sky" aria-hidden="true">
          <span className="town-sun" />
          <span className="town-cloud town-cloud--one" />
          <span className="town-cloud town-cloud--two" />
          <span className="town-hill town-hill--back" />
          <span className="town-hill town-hill--front" />
          <span className="town-ground" />
          <span className="town-path town-path--horizontal" />
          <span className="town-path town-path--vertical" />
          <span className="town-tree town-tree--one" />
          <span className="town-tree town-tree--two" />
          <span className="town-tree town-tree--three" />
          <span className="town-tree town-tree--four" />
        </div>

        <svg className="town-network" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          {visibleAgents.filter((agent) => agent !== 'orchestrator').map((agent) => {
            const meta = TOWN_META[agent]
            return (
              <line
                key={agent}
                className={`town-network-line town-network-line--${statusFor(agent)}`}
                x1={meta.x}
                y1={meta.y}
                x2={TOWN_META.orchestrator.x}
                y2={TOWN_META.orchestrator.y}
              />
            )
          })}
        </svg>

        <TownBuilding className="town-building--budget" label="LEDGER" />
        <TownBuilding className="town-building--transport" label="ROUTES" />
        <TownBuilding className="town-building--stay" label="STAYS" />
        <TownBuilding className="town-building--food" label="KITCHEN" />
        <TownBuilding className="town-building--activity" label="STUDIO" />
        <TownBuilding className="town-building--planning" label="WORKSHOP" />

        <div className="town-hall" aria-hidden="true">
          <span className="town-hall-flag">vibego</span>
          <span className="town-hall-roof" />
          <span className="town-hall-face"><i /><i /><b /></span>
          <span className="town-planning-table"><i /><i /><i /></span>
        </div>

        {visibleAgents.map((agent, index) => {
          const meta = TOWN_META[agent]
          const status = statusFor(agent)
          const isLatest = latestEvent?.agent === agent
          const showSpeech = status === 'running' || isLatest
          const message = isLatest ? eventMessage(latestEvent) : meta.running
          return (
            <div
              key={agent}
              className={`town-resident town-resident--${agent} town-resident--${status}${isLatest ? ' is-latest' : ''}`}
              style={{
                '--town-x': meta.x,
                '--town-y': meta.y,
                '--agent-delay': `${index * -0.11}s`,
              }}
            >
              {showSpeech && <span className="town-speech" aria-hidden="true">{message}</span>}
              <PixelResident color={meta.color} status={status} />
              <span className="town-resident-label">
                <strong>{meta.label}</strong>
                <small>{status === 'done' ? 'handoff sent' : status === 'running' ? 'working' : status === 'paused' ? 'paused' : 'waiting'}</small>
              </span>
            </div>
          )
        })}

        <div className="town-channel" role="log" aria-live="polite" aria-relevant="additions text">
          <div className="town-channel-head">
            <span><i /> Town channel</span>
            <b>{paused ? 'session paused' : runningCount ? `${runningCount} talking` : doneCount === visibleAgents.length ? 'plan ready' : 'opening channel'}</b>
          </div>
          <div className="town-channel-feed">
            {channelEvents.length ? channelEvents.map((event, index) => {
              const meta = TOWN_META[event.agent]
              return (
                <p key={`${event.agent}-${event.type}-${index}`}>
                  <span style={{ background: meta.color }}>{meta.short}</span>
                  <strong>{meta.label}</strong>
                  <em>{eventMessage(event)}</em>
                </p>
              )
            }) : (
              <p className="town-channel-empty">Town Hall is opening the shared mission brief…</p>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
