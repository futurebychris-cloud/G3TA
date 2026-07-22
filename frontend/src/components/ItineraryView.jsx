import { BedDouble, CalendarDays, Camera, Coffee, MapPin, PlaneLanding, PlaneTakeoff } from 'lucide-react'
import { useAccessibilitySettings } from '../accessibility/AccessibilityContext.jsx'
import LineFocusReader from './accessibility/LineFocusReader.jsx'
import ReadAloudButton from './accessibility/ReadAloudButton.jsx'
import {
  expandTravelAbbreviations,
  formatAccessibleDate,
  getTravelJargonExplanations,
  simplifySeniorTravelLanguage,
} from '../utils/accessibility.js'

const TYPE_META = {
  arrival: { label: 'Arrival', icon: PlaneLanding, tone: 'sky' },
  departure: { label: 'Departure', icon: PlaneTakeoff, tone: 'sky' },
  lodging: { label: 'Stay', icon: BedDouble, tone: 'violet' },
  meal: { label: 'Taste', icon: Coffee, tone: 'coral' },
  activity: { label: 'Explore', icon: Camera, tone: 'lime' },
}

function formatDayDate(value) {
  return formatAccessibleDate(value, { weekday: true, year: false })
}

export default function ItineraryView({ result }) {
  const { settings } = useAccessibilitySettings()
  const isSenior = settings.preset === 'senior'
  return (
    <div className="itinerary-view">
      <div className="panel-heading">
        <div>
          <span className="section-index">YOUR DAYS</span>
          <h2>A considered rhythm,<br />from touchdown to takeoff.</h2>
        </div>
        <p>{result.schedule.length} days shaped around your tastes, pace, and total budget.</p>
      </div>

      <div className="day-stack" aria-label="Day-by-day itinerary">
        {result.schedule.map((day, dayIndex) => (
          <article key={`${day.day}-${day.date}`} className="day-plan" aria-labelledby={`day-${day.day}-heading`}>
            <header className="day-plan-head">
              <div className="day-counter" aria-hidden="true"><small>DAY</small>{String(day.day).padStart(2, '0')}</div>
              <div>
                <p><CalendarDays size={14} aria-hidden="true" /> {formatDayDate(day.date)}</p>
                <h3 id={`day-${day.day}-heading`}>Day {day.day}: {day.title}</h3>
              </div>
              <span className="day-route-label">{dayIndex === 0 ? 'Begin here' : dayIndex === result.schedule.length - 1 ? 'Final chapter' : 'Keep exploring'}</span>
              <ReadAloudButton
                id={`itinerary-day-${day.day}`}
                label={`day ${day.day} itinerary`}
                text={[
                  `Day ${day.day}. ${formatDayDate(day.date)}. ${day.title}`,
                  ...day.items.flatMap((item) => [item.time, TYPE_META[item.type]?.label || item.type, item.title, item.detail]),
                ]}
              />
            </header>

            <ol className="day-events">
              {day.items.map((item, itemIndex) => {
                const meta = TYPE_META[item.type] || { label: item.type, icon: MapPin, tone: 'slate' }
                const ItemIcon = meta.icon
                const title = isSenior && settings.easyReading
                  ? simplifySeniorTravelLanguage(item.title, { explain: false })
                  : settings.easyReading ? expandTravelAbbreviations(item.title) : item.title
                const baseDetail = isSenior && settings.easyReading
                  ? simplifySeniorTravelLanguage(item.detail, { explain: false })
                  : settings.easyReading ? expandTravelAbbreviations(item.detail) : item.detail
                const jargon = isSenior && settings.easyReading
                  ? getTravelJargonExplanations(`${item.title}. ${item.detail}`)
                  : []
                const machineTime = /^\d{1,2}:\d{2}$/.test(item.time) ? `${day.date}T${item.time}` : undefined
                return (
                  <li className="event-row" key={`${item.time}-${itemIndex}`}>
                    <time dateTime={machineTime}>{item.time}</time>
                    <div className={`event-marker ${meta.tone}`} aria-hidden="true"><ItemIcon size={17} strokeWidth={1.8} /></div>
                    <div className="event-copy">
                      <span className="event-type">{meta.label}</span>
                      <h4>{title}</h4>
                      {baseDetail && <LineFocusReader text={baseDetail} />}
                      {jargon.length > 0 && (
                        <p className="travel-jargon-help"><strong>Helpful explanation:</strong> {jargon.join(' ')}</p>
                      )}
                      {isSenior && ['arrival', 'departure', 'lodging'].includes(item.type) && (
                        <ReadAloudButton
                          id={`important-travel-${day.day}-${itemIndex}`}
                          label={`${meta.label.toLowerCase()} information`}
                          text={[item.time, title, baseDetail, ...jargon]}
                        />
                      )}
                    </div>
                    <span className="event-index" aria-hidden="true">{String(itemIndex + 1).padStart(2, '0')}</span>
                  </li>
                )
              })}
            </ol>
          </article>
        ))}
      </div>
    </div>
  )
}
