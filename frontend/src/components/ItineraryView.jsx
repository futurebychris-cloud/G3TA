// Day-by-day itinerary (PRD §9 step 3). Renders the Orchestrator's synthesized schedule.
const TYPE_ICON = {
  arrival: '🛬',
  departure: '🛫',
  lodging: '🏨',
  meal: '🍽️',
  activity: '📸',
}

export default function ItineraryView({ result }) {
  return (
    <div>
      {result.summary && <p className="summary">{result.summary}</p>}

      <div className="itinerary">
        {result.schedule.map((day) => (
          <div key={day.day} className="day-card">
            <div className="day-head">
              <span className="day-num">Day {day.day}</span>
              <span className="day-date">{day.date}</span>
              <span className="day-title">{day.title}</span>
            </div>
            <ul className="timeline">
              {day.items.map((item, i) => (
                <li key={i}>
                  <span className="time">{item.time}</span>
                  <span className="item-icon">{TYPE_ICON[item.type] || '•'}</span>
                  <span className="item-body">
                    <strong>{item.title}</strong>
                    {item.detail && <span className="item-detail">{item.detail}</span>}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  )
}
