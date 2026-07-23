import { useEffect, useId, useState } from 'react'
import { Check, LoaderCircle, MessageCircle, Sparkles, X } from 'lucide-react'
import { parseTripDescription } from '../api.js'
import { useAccessibilitySettings } from '../accessibility/AccessibilityContext.jsx'
import ReadAloudButton from './accessibility/ReadAloudButton.jsx'
import VoiceInputButton from './accessibility/VoiceInputButton.jsx'

const PROMPT = 'Describe where you are leaving from, where you want to go, your dates, budget, number of travelers, and any preferences. You can type or use the microphone.'

export default function GuidedTripAssistant({ onApply }) {
  const { settings } = useAccessibilitySettings()
  const descriptionId = useId()
  const [open, setOpen] = useState(settings.preset === 'voiceFirst')
  const [description, setDescription] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (settings.preset === 'voiceFirst') setOpen(true)
  }, [settings.preset])

  async function buildDraft() {
    if (description.trim().length < 10) {
      setError('Add a little more detail so the assistant can build a useful draft.')
      return
    }
    setLoading(true)
    setError('')
    setResult(null)
    try {
      setResult(await parseTripDescription(description.trim()))
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setLoading(false)
    }
  }

  if (!open) {
    return (
      <button className="guided-trip-trigger" type="button" onClick={() => setOpen(true)}>
        <MessageCircle size={17} /> Describe or speak your trip instead
      </button>
    )
  }

  return (
    <section className="guided-trip-assistant" aria-labelledby="guided-trip-title">
      <div className="guided-trip-head">
        <div>
          <span className="section-index">VOICE OR TEXT SETUP</span>
          <h3 id="guided-trip-title">Tell us the trip in your own words</h3>
        </div>
        <div className="guided-trip-actions">
          <ReadAloudButton id="guided-trip-prompt" text={PROMPT} label="trip setup instructions" />
          <button type="button" className="dialog-close" onClick={() => setOpen(false)} aria-label="Close guided trip setup">
            <X size={18} />
          </button>
        </div>
      </div>
      <p>{PROMPT}</p>
      <div className="guided-description">
        <label className="sr-only" htmlFor={descriptionId}>Trip description</label>
        <textarea
          id={descriptionId}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder="For example: Two of us want to travel from Hangzhou to Shanghai from August 10 to 13, with a CNY 6,000 budget…"
          rows={4}
        />
        <VoiceInputButton
          label="Describe this trip by voice"
          onTranscript={(transcript) => setDescription((current) => (
            current.trim() ? `${current.trim()} ${transcript}` : transcript
          ))}
        />
      </div>
      <button type="button" className="guided-draft-button" onClick={buildDraft} disabled={loading}>
        {loading ? <><LoaderCircle className="spinner" size={16} /> Building a reviewable draft…</> : <><Sparkles size={16} /> Build draft</>}
      </button>
      {error && <p className="guided-error" role="alert">{error}</p>}
      {result && (
        <div className="guided-review" role="status">
          <strong>{result.summary}</strong>
          {result.missing?.length > 0 && (
            <p>Still needed in the form: {result.missing.join(', ')}.</p>
          )}
          {result.uncertain?.length > 0 && (
            <p>Please double-check: {result.uncertain.join(', ')}.</p>
          )}
          <button
            type="button"
            className="done-accessibility"
            onClick={() => {
              onApply(result.draft)
              setOpen(false)
            }}
          >
            <Check size={16} /> Apply draft to form
          </button>
        </div>
      )}
    </section>
  )
}
