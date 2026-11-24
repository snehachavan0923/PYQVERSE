interface LoadingStateProps {
  label?: string
  rows?: number
}

export function LoadingState({ label = 'Loading…', rows = 3 }: LoadingStateProps) {
  return (
    <div className="skeleton-stack" role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }).map((_, index) => (
        <div className="skeleton-block" key={index} />
      ))}
    </div>
  )
}

interface ErrorStateProps {
  message: string
  onRetry?: () => void
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <div className="error-state" role="alert">
      <strong>Something went wrong</strong>
      <p>{message}</p>
      {onRetry && (
        <button className="secondary-button compact-button" type="button" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}
