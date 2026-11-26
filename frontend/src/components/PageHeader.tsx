import type { ReactNode } from 'react'

interface PageHeaderProps {
  eyebrow?: string
  title: string
  description?: string
  meta?: ReactNode
  actions?: ReactNode
}

export default function PageHeader({ eyebrow, title, description, meta, actions }: PageHeaderProps) {
  return (
    <header className="page-header">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {description && <p className="muted">{description}</p>}
        {meta && <div className="page-meta">{meta}</div>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  )
}
