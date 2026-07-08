import { Link } from 'react-router-dom'

export interface BreadcrumbItem {
  label: string
  href?: string
}

interface BreadcrumbsProps {
  crumbs: BreadcrumbItem[]
}

export function Breadcrumbs({ crumbs }: BreadcrumbsProps) {
  if (crumbs.length === 0) return null

  return (
    <nav className="breadcrumbs" aria-label="Breadcrumb">
      <ol className="breadcrumbs-list">
        {crumbs.map((crumb, index) => {
          const isLast = index === crumbs.length - 1

          return (
            <li key={`${crumb.label}-${index}`} className="breadcrumbs-item">
              {index > 0 ? <span className="breadcrumbs-separator" aria-hidden="true">/</span> : null}
              {crumb.href && !isLast ? (
                <Link to={crumb.href} className="breadcrumbs-link">
                  {crumb.label}
                </Link>
              ) : (
                <span className="breadcrumbs-current" aria-current={isLast ? 'page' : undefined}>
                  {crumb.label}
                </span>
              )}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
