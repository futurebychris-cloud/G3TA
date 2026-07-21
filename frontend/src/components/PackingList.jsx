// Packing list + weather + pacing (PRD §9 step 3), from the Planning Agent.
export default function PackingList({ items, weather, pacing }) {
  return (
    <div className="packing">
      {weather && (
        <div className="weather-card">
          <h4>🌤 Weather outlook</h4>
          <p>{weather}</p>
        </div>
      )}
      {pacing && (
        <div className="weather-card">
          <h4>⏱ Pacing notes</h4>
          <p>{pacing}</p>
        </div>
      )}
      <h4>🎒 Packing list</h4>
      <ul className="packing-grid">
        {items.map((item, i) => (
          <li key={i}><label><input type="checkbox" /> {item}</label></li>
        ))}
      </ul>
    </div>
  )
}
