interface ContentActionsProps {
  onView: () => void
  onDownload: () => void
  busy?: boolean
  viewDisabled?: boolean
  label?: string
  viewHint?: string
  withLabels?: boolean
}

function EyeIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M2.1 12a9.9 9.9 0 0 1 19.8 0 9.9 9.9 0 0 1-19.8 0Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  )
}

function DownloadIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 3v12" />
      <path d="m7 10 5 5 5-5" />
      <path d="M5 21h14" />
    </svg>
  )
}

export default function ContentActions({
  onView,
  onDownload,
  busy = false,
  viewDisabled = false,
  label,
  viewHint,
  withLabels = false,
}: ContentActionsProps) {
  const suffix = label ? ` ${label}` : ''
  const buttonClass = withLabels ? 'icon-button action-button' : 'icon-button'
  return (
    <div className="content-actions">
      <button
        className={buttonClass}
        type="button"
        aria-label={`View PDF${suffix}`}
        title={viewHint ?? 'View PDF in a new tab'}
        disabled={busy || viewDisabled}
        onClick={onView}
      >
        <EyeIcon />
        {withLabels && <span className="action-label">Preview</span>}
      </button>
      <button
        className={buttonClass}
        type="button"
        aria-label={`Download${suffix}`}
        title="Download file"
        disabled={busy}
        onClick={onDownload}
      >
        <DownloadIcon />
        {withLabels && <span className="action-label">Download</span>}
      </button>
    </div>
  )
}
