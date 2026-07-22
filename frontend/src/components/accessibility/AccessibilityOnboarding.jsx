import { useRef } from 'react'
import { Accessibility, ArrowRight } from 'lucide-react'
import { useAccessibilitySettings } from '../../accessibility/AccessibilityContext.jsx'
import AccessibleDialog from './AccessibleDialog.jsx'
import AccessibilityPresetSelector from './AccessibilityPresetSelector.jsx'

export default function AccessibilityOnboarding() {
  const { settings, applyPreset, completeOnboarding } = useAccessibilitySettings()
  const continueRef = useRef(null)

  function useStandard() {
    applyPreset('standard')
    completeOnboarding()
  }

  return (
    <AccessibleDialog
      open={!settings.onboardingComplete}
      onClose={completeOnboarding}
      initialFocusRef={continueRef}
      labelledBy="accessibility-onboarding-title"
      describedBy="accessibility-onboarding-description"
      className="accessibility-panel onboarding-panel"
      closeOnBackdrop={false}
    >
      <header className="onboarding-head">
        <span className="onboarding-icon" aria-hidden="true"><Accessibility size={25} /></span>
        <span className="section-index">WELCOME TO G3TA</span>
        <h2 id="accessibility-onboarding-title">How should your trip planner feel?</h2>
        <p id="accessibility-onboarding-description">
          Choose a starting point. You can change every option later from the Accessibility button.
        </p>
      </header>
      <div className="onboarding-presets">
        <AccessibilityPresetSelector />
      </div>
      <footer className="accessibility-panel-actions onboarding-actions">
        <button className="reset-accessibility" type="button" onClick={useStandard}>Use standard settings</button>
        <button ref={continueRef} className="done-accessibility" type="button" onClick={completeOnboarding}>
          Continue <ArrowRight size={16} aria-hidden="true" />
        </button>
      </footer>
    </AccessibleDialog>
  )
}
