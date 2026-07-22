import { describe, expect, it } from 'vitest'
import {
  EASY_READING_INSTRUCTION,
  explainTravelJargon,
  expandTravelAbbreviations,
  getImmediateNextStep,
  prepareTextForSpeech,
  simplifySeniorTravelLanguage,
  splitReadableLines,
} from './accessibility.js'

describe('accessible travel formatting', () => {
  it('keeps explicit factual-preservation requirements in the easy-reading prompt', () => {
    expect(EASY_READING_INSTRUCTION).toContain('Preserve every date, time, price, location, warning, duration, flight number')
    expect(EASY_READING_INSTRUCTION).toContain('Do not add facts')
    expect(EASY_READING_INSTRUCTION).toContain('travel jargon')
  })

  it('expands known abbreviations without removing their codes', () => {
    expect(expandTravelAbbreviations('JFK to NRT')).toBe('John F. Kennedy International Airport (JFK) to Narita International Airport (NRT)')
  })

  it('prepares plain speech text and ignores markup', () => {
    const spoken = prepareTextForSpeech(['<b>Flight</b>', 'JFK → NRT', 'USD 500'])
    expect(spoken).not.toContain('<b>')
    expect(spoken).toContain('United States dollars (USD) 500')
  })

  it('splits sentences into readable lines without changing their text', () => {
    expect(splitReadableLines('First fact. Second fact!')).toEqual(['First fact.', 'Second fact!'])
  })

  it('adds brief jargon explanations while preserving the original details', () => {
    const source = 'Transfer to the JR Yamanote Line at platform 2.'
    const simplified = simplifySeniorTravelLanguage(source)
    expect(simplified).toContain('JR Yamanote Line')
    expect(simplified).toContain('platform 2')
    expect(simplified).toContain('Change to')
    expect(explainTravelJargon('Go to the boarding gate.')).toContain('place where you enter your flight')
  })

  it('summarizes only the immediate next itinerary item', () => {
    const next = getImmediateNextStep({
      schedule: [{
        day: 1,
        date: '2026-07-22',
        items: [
          { time: '08:00', title: 'Breakfast', detail: 'Eat at the hotel.' },
          { time: '11:30', title: 'Board Train 2', detail: 'Walk 4 minutes. Ride 3 stops. Exit at Station A.' },
        ],
      }],
    }, new Date(2026, 6, 22, 10, 0))
    expect(next.lines).toEqual(['11:30', 'Board Train 2', 'Walk 4 minutes.', 'Ride 3 stops.', 'Exit at Station A.'])
    expect(next.lines).not.toContain('Breakfast')
  })
})
