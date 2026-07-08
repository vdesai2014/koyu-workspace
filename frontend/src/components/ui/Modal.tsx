import { useEffect, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

interface ModalProps {
  title: string
  actions?: ReactNode
  onClose: () => void
  children: ReactNode
  panelClassName?: string
  bodyClassName?: string
}

export function Modal({
  title,
  actions,
  onClose,
  children,
  panelClassName = '',
  bodyClassName = '',
}: ModalProps) {
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose()
      }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [onClose])

  if (!mounted) {
    return null
  }

  return createPortal(
    <div className="modal-backdrop" onClick={(event) => event.target === event.currentTarget && onClose()}>
      <div className={`modal-panel ${panelClassName}`.trim()}>
        <div className="modal-header">
          <h2>{title}</h2>
          <div className="modal-header-actions">
            {actions}
            <button className="modal-close" onClick={onClose} aria-label="Close modal">
              ×
            </button>
          </div>
        </div>
        <div className={`modal-body ${bodyClassName}`.trim()}>{children}</div>
      </div>
    </div>,
    document.body,
  )
}
