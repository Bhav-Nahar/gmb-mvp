import React from 'react'

interface BreadcrumbsProps {
  name: string
  city?: string | null
  state?: string | null
  homeUrl: string
}

// Visible breadcrumb trail: Home > State > City > Business. Improves SEO context
// and navigation. A matching BreadcrumbList JSON-LD is emitted from the page.
export default function Breadcrumbs({ name, city, state, homeUrl }: BreadcrumbsProps) {
  const crumbs = [
    state || null,
    city || null,
    name,
  ].filter(Boolean) as string[]

  return (
    <nav aria-label="Breadcrumb" className="bg-background border-b border-border pt-3 pb-3">
      <ol className="max-w-6xl mx-auto px-4 sm:px-8 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs sm:text-sm text-muted-foreground">
        <li>
          <a href={homeUrl} className="hover:text-primary transition-colors font-medium">Home</a>
        </li>
        {crumbs.map((c, i) => {
          const isLast = i === crumbs.length - 1
          return (
            <li key={i} className="flex items-center gap-2">
              <span className="text-muted-foreground/40">/</span>
              {isLast
                ? <span className="text-foreground font-semibold truncate max-w-[60vw]" aria-current="page">{c}</span>
                : <span>{c}</span>}
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
