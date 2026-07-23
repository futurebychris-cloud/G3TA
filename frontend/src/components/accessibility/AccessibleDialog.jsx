import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'

export default function AccessibleDialog({
  open,
  onClose,
  returnFocusRef,
  initialFocusRef,
  labelledBy,
  describedBy,
  className = '',
  children,
  closeOnBackdrop = true,
}) {
  const dialogRef = useRef(null)
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  useEffect(() => {
    if (!open) return undefined
    const previouslyFocused = document.activeElement
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const fallbackFocus = dialogRef.current?.querySelector(
      'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
    )
    ;(initialFocusRef?.current || fallbackFocus)?.focus()

    function keydown(event) {
      if (event.key === 'Escape') {
        event.preventDefault()
        onCloseRef.current()
        return
      }
      if (event.key !== 'Tab') return
      const focusable = dialogRef.current?.querySelectorAll(
        'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
      )
      if (!focusable?.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', keydown)
    return () => {
      document.removeEventListener('keydown', keydown)
      document.body.style.overflow = previousOverflow
      const returnTarget = returnFocusRef?.current || previouslyFocused
      if (returnTarget && typeof returnTarget.focus === 'function') returnTarget.focus()
    }
  }, [initialFocusRef, open, returnFocusRef])

  if (!open) return null
  return createPortal(
    <div
      className="accessibility-overlay"
      onMouseDown={(event) => closeOnBackdrop && event.target === event.currentTarget && onClose()}
    >
      <section
        ref={dialogRef}
        className={className}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        aria-describedby={describedBy}
      >
        {children}
      </section>
    </div>,
    document.body,
  )
}
