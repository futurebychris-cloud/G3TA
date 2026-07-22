import { useState } from 'react'
import { useAccessibilitySettings } from '../../accessibility/AccessibilityContext.jsx'
import { splitReadableLines } from '../../utils/accessibility.js'

export default function LineFocusReader({ text, as: Element = 'p', className = '' }) {
  const { settings } = useAccessibilitySettings()
  const [activeLine, setActiveLine] = useState(null)
  const lines = splitReadableLines(text)
  const enabled = settings.lineFocus !== 'off' && lines.length > 1

  function moveFocus(event) {
    if (!enabled || !['ArrowDown', 'ArrowUp'].includes(event.key)) return
    event.preventDefault()
    const direction = event.key === 'ArrowDown' ? 1 : -1
    setActiveLine((current) => Math.min(lines.length - 1, Math.max(0, (current ?? 0) + direction)))
  }

  if (!lines.length) return null
  return (
    <Element
      className={`line-focus-reader ${className}`.trim()}
      data-focus-enabled={enabled}
      data-active-line={activeLine === null ? 'none' : activeLine}
      tabIndex={enabled ? 0 : undefined}
      onFocus={() => enabled && activeLine === null && setActiveLine(0)}
      onKeyDown={moveFocus}
    >
      {lines.map((line, index) => {
        const range = settings.lineFocus === 'three' ? 1 : 0
        const highlighted = activeLine === null || Math.abs(index - activeLine) <= range
        return (
          <span
            className={highlighted ? 'reading-line highlighted' : 'reading-line dimmed'}
            key={`${line}-${index}`}
            onMouseEnter={() => enabled && setActiveLine(index)}
            onClick={() => enabled && setActiveLine(index)}
          >
            {line}{index < lines.length - 1 ? ' ' : ''}
          </span>
        )
      })}
    </Element>
  )
}
