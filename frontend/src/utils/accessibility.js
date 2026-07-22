export const EASY_READING_INSTRUCTION = `Rewrite the result for easy reading.

Requirements:
- Use plain language.
- Use short sentences.
- Put one main idea on each line.
- Use clear headings.
- Explain unfamiliar travel abbreviations.
- Briefly explain travel jargon such as boarding gate, layover, terminal, platform, metro, immigration, and JR Pass.
- Put the most important information first.
- Preserve every date, time, price, location, warning, duration, flight number, and factual detail exactly.
- Do not add facts that are not present in the source data.`

const TRAVEL_ABBREVIATIONS = {
  JFK: 'John F. Kennedy International Airport (JFK)',
  LGA: 'LaGuardia Airport (LGA)',
  EWR: 'Newark Liberty International Airport (EWR)',
  NRT: 'Narita International Airport (NRT)',
  HND: 'Haneda Airport (HND)',
  PVG: 'Shanghai Pudong International Airport (PVG)',
  SHA: 'Shanghai Hongqiao International Airport (SHA)',
  LHR: 'London Heathrow Airport (LHR)',
  CDG: 'Charles de Gaulle Airport (CDG)',
  USD: 'United States dollars (USD)',
  EUR: 'euros (EUR)',
  GBP: 'British pounds (GBP)',
  CNY: 'Chinese yuan (CNY)',
  JPY: 'Japanese yen (JPY)',
}

export function expandTravelAbbreviations(value) {
  return String(value ?? '').replace(/\b[A-Z]{3}\b/g, (code) => TRAVEL_ABBREVIATIONS[code] || code)
}

export function splitReadableLines(value) {
  const text = String(value ?? '').trim()
  if (!text) return []
  return text.split(/(?<=[.!?])\s+|\n+/).map((line) => line.trim()).filter(Boolean)
}

export function prepareTextForSpeech(value) {
  const values = Array.isArray(value) ? value : [value]
  return values
    .flat(Infinity)
    .filter((item) => item !== null && item !== undefined && item !== false)
    .map((item) => expandTravelAbbreviations(String(item).replace(/<[^>]*>/g, ' ')))
    .join('. ')
    .replace(/→/g, ' to ')
    .replace(/&/g, ' and ')
    .replace(/\s+/g, ' ')
    .trim()
}

export function formatAccessibleDate(value, options = {}) {
  const date = new Date(`${value}T00:00:00`)
  if (Number.isNaN(date.getTime())) return String(value ?? '')
  return date.toLocaleDateString('en', {
    weekday: options.weekday ? 'long' : undefined,
    month: options.short ? 'short' : 'long',
    day: 'numeric',
    year: options.year === false ? undefined : 'numeric',
  })
}

export function formatAccessibleMoney(currency, amount) {
  const numeric = Number(amount)
  const formatted = Number.isFinite(numeric) ? numeric.toLocaleString(undefined, { maximumFractionDigits: 2 }) : amount
  return `${currency} ${formatted}`
}

const TRAVEL_JARGON = [
  ['JR Pass', 'JR Pass means a prepaid rail pass for eligible JR trains.'],
  ['boarding gate', 'A boarding gate is the place where you enter your flight.'],
  ['immigration', 'Immigration is the passport check when entering or leaving a country.'],
  ['layover', 'A layover is waiting at an airport between flights.'],
  ['terminal', 'A terminal is the airport building used by your flight.'],
  ['platform', 'A platform is where you wait to board a train.'],
  ['metro', 'Metro means the local subway or underground train.'],
]

export function getTravelJargonExplanations(value) {
  const text = String(value ?? '').trim()
  if (!text) return []
  return TRAVEL_JARGON
    .filter(([term]) => new RegExp(`\\b${term.replace(/\s+/g, '\\s+')}\\b`, 'i').test(text))
    .map(([, explanation]) => explanation)
}

export function explainTravelJargon(value) {
  const text = String(value ?? '').trim()
  if (!text) return text
  const explanations = getTravelJargonExplanations(text)
  return explanations.length ? `${text} ${explanations.join(' ')}` : text
}

export function simplifySeniorTravelLanguage(value, { explain = true } = {}) {
  const simplified = expandTravelAbbreviations(value)
    .replace(/\btransfer to\b/gi, 'Change to')
    .replace(/\bproceed to\b/gi, 'Go to')
  return explain ? explainTravelJargon(simplified) : simplified
}

function localDateKey(date = new Date()) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function getImmediateNextStep(result, now = new Date()) {
  const schedule = result?.schedule || []
  if (!schedule.length) return null
  const today = localDateKey(now)
  const day = schedule.find((entry) => entry.date === today) || schedule[0]
  const items = day.items || []
  let item = items[0]
  if (day.date === today) {
    const minutesNow = now.getHours() * 60 + now.getMinutes()
    item = items.find((entry) => {
      const match = String(entry.time || '').match(/^(\d{1,2}):(\d{2})$/)
      return match && Number(match[1]) * 60 + Number(match[2]) >= minutesNow
    }) || items[items.length - 1]
  }
  if (!item) return null
  const detailLines = splitReadableLines(item.detail).slice(0, 3)
  const lines = [item.time, item.title, ...detailLines].filter(Boolean).slice(0, 5)
  return {
    day: day.day,
    date: day.date,
    title: item.title,
    lines,
    speech: [`Next step for day ${day.day}`, ...lines],
  }
}
