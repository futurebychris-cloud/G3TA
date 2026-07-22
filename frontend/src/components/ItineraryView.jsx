import { BedDouble, CalendarDays, Camera, Coffee, ImageOff, MapPin, PlaneLanding, PlaneTakeoff } from 'lucide-react'

const TYPE_META = {
  arrival: { label: 'Arrival', icon: PlaneLanding, tone: 'sky' },
  departure: { label: 'Departure', icon: PlaneTakeoff, tone: 'sky' },
  lodging: { label: 'Stay', icon: BedDouble, tone: 'violet' },
  meal: { label: 'Taste', icon: Coffee, tone: 'coral' },
  activity: { label: 'Explore', icon: Camera, tone: 'lime' },
}

// Image lookup: maps item titles to available images from agent data
function findImage(item, imageMap) {
  if (!imageMap || !item?.title) return null
  const key = item.title.toLowerCase().trim()
  for (const [name, img] of Object.entries(imageMap)) {
    if (name.toLowerCase().includes(key) || key.includes(name.toLowerCase())) {
      return Array.isArray(img) ? img[0] : img
    }
  }
  return null
}

function formatDayDate(value) {
  return new Date(`${value}T00:00:00`).toLocaleDateString('en', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  })
}

export default function ItineraryView({ result }) {
  // Build image map from agent outputs
  const imageMap = {}
  const agentOutputs = result?.agent_outputs || {}

  // Hotel images
  const housing = agentOutputs.housing
  if (housing) {
    const rec = housing.recommended
    if (rec?.images?.length > 0) {
      imageMap[rec.name] = rec.images
    }
    // Also check all options for images
    if (housing.options) {
      for (const opt of housing.options) {
        if (opt.images?.length > 0 && !imageMap[opt.name]) {
          imageMap[opt.name] = opt.images
        }
      }
    }
  }

  // Activity images (if activity agent supplies them)
  const activity = agentOutputs.activity
  if (activity?.recommended) {
    for (const act of activity.recommended) {
      if (act.images?.length > 0) {
        imageMap[act.name] = act.images
      }
      // Check for image_url or thumbnail fields
      if (act.image_url && !imageMap[act.name]) {
        imageMap[act.name] = [act.image_url]
      }
      if (act.thumbnail && !imageMap[act.name]) {
        imageMap[act.name] = [act.thumbnail]
      }
    }
  }

  const hasAnyImages = Object.keys(imageMap).length > 0

  return (
    <div className="itinerary-view">
      <div className="panel-heading">
        <div>
          <span className="section-index">YOUR DAYS</span>
          <h2>A considered rhythm,<br />from touchdown to takeoff.</h2>
        </div>
        <p>{result.schedule.length} days shaped around your tastes, pace, and total budget.</p>
      </div>

      <div className="day-stack">
        {result.schedule.map((day, dayIndex) => (
          <article key={`${day.day}-${day.date}`} className="day-plan">
            <header className="day-plan-head">
              <div className="day-counter"><small>DAY</small>{String(day.day).padStart(2, '0')}</div>
              <div>
                <p><CalendarDays size={14} /> {formatDayDate(day.date)}</p>
                <h3>{day.title}</h3>
              </div>
              <span className="day-route-label">{dayIndex === 0 ? 'Begin here' : dayIndex === result.schedule.length - 1 ? 'Final chapter' : 'Keep exploring'}</span>
            </header>

            <div className="day-events">
              {day.items.map((item, itemIndex) => {
                const meta = TYPE_META[item.type] || { label: item.type, icon: MapPin, tone: 'slate' }
                const ItemIcon = meta.icon
                const imageUrl = findImage(item, imageMap)

                return (
                  <div className="event-row" key={`${item.time}-${itemIndex}`}>
                    <time>{item.time}</time>
                    <div className={`event-marker ${meta.tone}`}><ItemIcon size={17} strokeWidth={1.8} /></div>
                    <div className="event-copy">
                      <span className="event-type">{meta.label}</span>
                      <h4>{item.title}</h4>
                      {item.detail && <p>{item.detail}</p>}
                    </div>
                    <div className="event-thumb">
                      {imageUrl ? (
                        <img
                          src={imageUrl}
                          alt={item.title}
                          loading="lazy"
                          onError={(e) => { e.target.style.display = 'none' }}
                        />
                      ) : (
                        <div className="event-thumb-placeholder">
                          {hasAnyImages ? <ImageOff size={12} /> : null}
                        </div>
                      )}
                    </div>
                    <span className="event-index">{String(itemIndex + 1).padStart(2, '0')}</span>
                  </div>
                )
              })}
            </div>
          </article>
        ))}
      </div>
    </div>
  )
}
