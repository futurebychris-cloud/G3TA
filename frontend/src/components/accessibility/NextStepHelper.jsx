import { useRef, useState } from 'react'
import { ArrowRight, CircleHelp, X } from 'lucide-react'
import { formatAccessibleDate, getImmediateNextStep } from '../../utils/accessibility.js'
import AccessibleDialog from './AccessibleDialog.jsx'
import ReadAloudButton from './ReadAloudButton.jsx'

export default function NextStepHelper({ result }) {
  const [open, setOpen] = useState(false)
  const triggerRef = useRef(null)
  const closeRef = useRef(null)
  const nextStep = getImmediateNextStep(result)
  if (!nextStep) return null

  return (
    <>
      <button ref={triggerRef} className="next-step-trigger" type="button" onClick={() => setOpen(true)}>
        <CircleHelp size={23} aria-hidden="true" />
        <span>What do I do next?</span>
      </button>
      <AccessibleDialog
        open={open}
        onClose={() => setOpen(false)}
        returnFocusRef={triggerRef}
        initialFocusRef={closeRef}
        labelledBy="next-step-title"
        describedBy="next-step-date"
        className="next-step-dialog"
      >
        <button ref={closeRef} className="dialog-close" type="button" onClick={() => setOpen(false)} aria-label="Close next step">
          <X size={20} aria-hidden="true" />
        </button>
        <span className="section-index">NEXT STEP</span>
        <h2 id="next-step-title">Do this next</h2>
        <p id="next-step-date">Day {nextStep.day}. {formatAccessibleDate(nextStep.date, { weekday: true })}</p>
        <ol className="next-step-lines">
          {nextStep.lines.map((line, index) => (
            <li key={`${line}-${index}`}><ArrowRight size={17} aria-hidden="true" /><span>{line}</span></li>
          ))}
        </ol>
        <ReadAloudButton id="next-step" label="next step" text={nextStep.speech} />
      </AccessibleDialog>
    </>
  )
}
