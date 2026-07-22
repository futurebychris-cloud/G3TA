import { Accessibility } from 'lucide-react'

export default function AccessibilityButton({ onClick, buttonRef }) {
  return (
    <button
      ref={buttonRef}
      className="accessibility-trigger"
      type="button"
      onClick={onClick}
      aria-haspopup="dialog"
      aria-label="Accessibility options"
    >
      <Accessibility size={19} aria-hidden="true" />
      <span>Accessibility</span>
    </button>
  )
}
