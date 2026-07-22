import { useRef } from 'react'
import AccessibleDialog from './AccessibleDialog.jsx'

export default function ConfirmationDialog({ open, title, description, onCancel, onConfirm, returnFocusRef }) {
  const cancelRef = useRef(null)
  return (
    <AccessibleDialog
      open={open}
      onClose={onCancel}
      returnFocusRef={returnFocusRef}
      initialFocusRef={cancelRef}
      labelledBy="confirmation-title"
      describedBy="confirmation-description"
      className="confirmation-dialog"
    >
      <h2 id="confirmation-title">{title}</h2>
      <p id="confirmation-description">{description}</p>
      <div className="confirmation-actions">
        <button ref={cancelRef} type="button" onClick={onCancel}>Cancel</button>
        <button className="confirm-continue" type="button" onClick={onConfirm}>Continue</button>
      </div>
    </AccessibleDialog>
  )
}
