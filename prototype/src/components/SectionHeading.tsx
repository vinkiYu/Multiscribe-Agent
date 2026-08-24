import { type ReactElement, type ReactNode } from 'react'

export function SectionHeading({
  title,
  description,
  actions,
}: {
  icon?: ReactNode
  title: string
  description?: string
  actions?: ReactNode
}): ReactElement {
  return (
    <>
      <header className="page-rail">
        <div className="page-rail-info">
          <div>
            <h1 className="page-rail-title">{title}</h1>
            {description && <p className="page-rail-description">{description}</p>}
          </div>
        </div>
        {actions && <div className="page-rail-actions">{actions}</div>}
      </header>
      <div className="page-rail-spacer" aria-hidden="true" />
    </>
  )
}