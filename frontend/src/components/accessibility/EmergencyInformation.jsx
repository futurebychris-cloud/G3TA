import { useRef, useState } from 'react'
import { PhoneCall, ShieldAlert, X } from 'lucide-react'
import AccessibleDialog from './AccessibleDialog.jsx'
import ReadAloudButton from './ReadAloudButton.jsx'

const UNAVAILABLE = 'Not provided. Verify and save this information before travel.'

export default function EmergencyInformation({ result }) {
  const [open, setOpen] = useState(false)
  const triggerRef = useRef(null)
  const closeRef = useRef(null)
  const hotel = result.agent_outputs?.housing?.recommended || {}
  const address = hotel.address || (hotel.area ? `${hotel.area}. Area only; verify the full street address.` : UNAVAILABLE)
  const fields = [
    ['Hotel name', hotel.name || UNAVAILABLE],
    ['Hotel address', address],
    ['Hotel phone', hotel.phone || UNAVAILABLE],
    ['Emergency contact', result.emergency_contact || UNAVAILABLE],
    ['Local emergency number', result.local_emergency_number || UNAVAILABLE],
    ['Embassy information', result.embassy_information || UNAVAILABLE],
    ['Offline instructions', 'Save a screenshot of this card. Keep a paper copy of verified hotel and emergency contacts.'],
    ['Taxi destination in local language', hotel.local_name || hotel.address_local || UNAVAILABLE],
  ]

  return (
    <>
      <button ref={triggerRef} className="senior-action-button emergency-button" type="button" onClick={() => setOpen(true)}>
        <ShieldAlert size={20} aria-hidden="true" /> Emergency Information
      </button>
      <AccessibleDialog
        open={open}
        onClose={() => setOpen(false)}
        returnFocusRef={triggerRef}
        initialFocusRef={closeRef}
        labelledBy="emergency-information-title"
        describedBy="emergency-information-description"
        className="accessibility-panel emergency-dialog"
      >
        <header className="accessibility-panel-head">
          <div>
            <span className="section-index">KEEP THIS HANDY</span>
            <h2 id="emergency-information-title">Emergency Information</h2>
            <p id="emergency-information-description">Verify missing details and save this card before leaving your hotel.</p>
          </div>
          <button ref={closeRef} className="dialog-close" type="button" onClick={() => setOpen(false)} aria-label="Close emergency information">
            <X size={20} aria-hidden="true" />
          </button>
        </header>
        <div className="emergency-read-action">
          <ReadAloudButton id="emergency-card" label="emergency information" text={fields.flat()} />
        </div>
        <dl className="emergency-details">
          {fields.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
        <footer className="emergency-footer">
          <PhoneCall size={19} aria-hidden="true" />
          <p>In immediate danger, ask a nearby staff member to contact verified local emergency services.</p>
        </footer>
      </AccessibleDialog>
    </>
  )
}
